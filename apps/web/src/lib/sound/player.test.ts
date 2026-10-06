import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setSoundEnabled } from '@/preferences/sound';
import {
  armAudioUnlock,
  chooseSound,
  endLoop,
  FADE_IN,
  FADE_OUT,
  isSoundPlaying,
  LAST_LOOP_MIN,
  loopSound,
  resetAudio,
  STOP_FADE,
  stopSound,
  subscribeSoundPlaying,
  unlockAudio,
  useSoundPlaying,
  VOLUME,
  WAKE_WAIT_MS,
} from './player';

/** A gain parameter that records what was scheduled on it. */
class FakeParam {
  value = 1;
  steps: [string, number, number][] = [];
  setValueAtTime(value: number, at: number) {
    this.steps.push(['set', value, at]);
    this.value = value;
  }
  linearRampToValueAtTime(value: number, at: number) {
    this.steps.push(['ramp', value, at]);
  }
  cancelScheduledValues(at: number) {
    this.steps.push(['cancel', 0, at]);
  }
}

class FakeSource extends EventTarget {
  buffer: { duration: number } | null = null;
  loop = false;
  started: number | null = null;
  stopped: number | null = null;
  connect = vi.fn();
  start(at: number) {
    this.started = at;
  }
  stop(at: number) {
    if (this.stopped !== null) {
      throw new Error('stopped twice');
    }
    this.stopped = at;
  }
}

class FakeContext {
  static made: FakeContext[] = [];
  static startState: AudioContextState = 'running';
  /** A browser that leaves a wake without a tap unanswered (iOS after the camera, Chrome with no gesture). */
  static hold = false;
  state: AudioContextState = FakeContext.startState;
  currentTime = 10;
  destination = {};
  sources: FakeSource[] = [];
  gains: { gain: FakeParam; connect: ReturnType<typeof vi.fn> }[] = [];
  decodeAudioData = vi.fn(async () => ({ duration: 3 }));
  resume = vi.fn(async () => {
    if (FakeContext.hold) {
      return new Promise<void>(() => undefined);
    }
    this.state = 'running';
  });
  constructor() {
    FakeContext.made.push(this);
  }
  createBufferSource() {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
  createBuffer() {
    return { duration: 0 };
  }
  createGain() {
    const node = { gain: new FakeParam(), connect: vi.fn() };
    this.gains.push(node);
    return node;
  }
}

function serve(response: Response | Error) {
  const fetch = vi.fn(async () => {
    if (response instanceof Error) {
      throw response;
    }
    return response.clone();
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const mp3 = () => new Response(new Blob(['sound']), { status: 200 });
const context = () => FakeContext.made[0] as FakeContext;
const played = () => context().sources.filter((source) => source.buffer?.duration === 3);

beforeEach(() => {
  resetAudio();
  FakeContext.made = [];
  FakeContext.startState = 'running';
  FakeContext.hold = false;
  window.localStorage.clear();
  vi.stubGlobal('AudioContext', FakeContext);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('loopSound', () => {
  it('fetches the file once and loops it after a fade in', async () => {
    const fetch = serve(mp3());
    await loopSound('/sounds/ontology/E006');

    expect(fetch).toHaveBeenCalledOnce();
    const [source] = played();
    expect(source?.started).toBe(10);
    expect(source?.loop).toBe(true);
    expect(source?.stopped).toBeNull();
    expect(context().gains[0]?.gain.steps).toEqual([
      ['set', 0, 10],
      ['ramp', VOLUME, 10 + FADE_IN],
    ]);
    source?.dispatchEvent(new Event('ended'));
    // Played again from memory: no second download.
    await loopSound('/sounds/ontology/E006');
    expect(fetch).toHaveBeenCalledOnce();
    expect(played()).toHaveLength(2);
  });

  it('keeps the fade in inside a very short sound', async () => {
    serve(mp3());
    await loopSound('/sounds/a');
    context().decodeAudioData.mockResolvedValueOnce({ duration: 0.3 });
    await loopSound('/sounds/b');
    const steps = context().gains[1]?.gain.steps ?? [];
    expect(steps[1]).toEqual(['ramp', VOLUME, 10.1]);
  });

  it('never starts a sound stopped while its file came', async () => {
    const fetch = serve(mp3());
    fetch.mockImplementationOnce(async () => {
      stopSound();
      return mp3();
    });
    await loopSound('/sounds/a');
    fetch.mockImplementationOnce(async () => {
      endLoop();
      return mp3();
    });
    await loopSound('/sounds/b');
    expect(played()).toHaveLength(0);
  });

  it('fades out the sound still playing when another starts', async () => {
    serve(mp3());
    await loopSound('/sounds/a');
    await loopSound('/sounds/b');
    const [first, second] = played();
    expect(first?.stopped).toBe(10 + STOP_FADE);
    expect(second?.stopped).toBeNull();
  });

  it('wakes a sleeping context, and stays quiet when the browser keeps it locked', async () => {
    serve(mp3());
    FakeContext.startState = 'suspended';
    await loopSound('/sounds/a');
    expect(context().resume).toHaveBeenCalled();
    expect(played()).toHaveLength(1);

    resetAudio();
    FakeContext.made = [];
    FakeContext.startState = 'suspended';
    await loopSound('/sounds/a');
    context().resume.mockImplementation(async () => {});
    context().state = 'suspended';
    await loopSound('/sounds/b');
    expect(context().sources.filter((s) => s.started !== null)).toHaveLength(1);
  });

  it('stays quiet when switched off, before or while the file comes', async () => {
    const fetch = serve(mp3());
    setSoundEnabled(false);
    await loopSound('/sounds/a');
    expect(fetch).not.toHaveBeenCalled();

    setSoundEnabled(true);
    fetch.mockImplementationOnce(async () => {
      setSoundEnabled(false);
      return mp3();
    });
    await loopSound('/sounds/b');
    expect(played()).toHaveLength(0);
  });

  it('ends quietly with no sound, no network, a bad file or no Web Audio', async () => {
    serve(new Response('', { status: 404 }));
    await loopSound('/sounds/missing');
    serve(new TypeError('offline'));
    await loopSound('/sounds/a');
    serve(mp3());
    context().decodeAudioData.mockRejectedValueOnce(new Error('not audio'));
    await loopSound('/sounds/b');
    expect(played()).toHaveLength(0);

    resetAudio();
    vi.stubGlobal('AudioContext', undefined);
    await expect(loopSound('/sounds/a')).resolves.toBeUndefined();
    expect(() => unlockAudio()).not.toThrow();
  });

  it('forgets the oldest decoded sound once it holds eight', async () => {
    const fetch = serve(mp3());
    for (let n = 0; n < 9; n += 1) {
      await loopSound(`/sounds/${n}`);
    }
    await loopSound('/sounds/0');
    expect(fetch).toHaveBeenCalledTimes(10);
  });
});

describe('endLoop', () => {
  const ending = async (duration: number, elapsed: number) => {
    serve(mp3());
    await loopSound('/sounds/a');
    context().decodeAudioData.mockResolvedValueOnce({ duration });
    await loopSound(`/sounds/${duration}`);
    context().currentTime = 10 + elapsed;
    endLoop();
    const source = context().sources.at(-1);
    return { stopped: source?.stopped ?? null, steps: context().gains.at(-1)?.gain.steps ?? [] };
  };

  it('ends with the loop playing when enough of it is left, fading out before', async () => {
    // 1 s into a 6 s loop: 5 s left.
    const { stopped, steps } = await ending(6, 1);
    expect(stopped).toBe(16);
    expect(steps.slice(-2)).toEqual([
      ['set', VOLUME, 16 - FADE_OUT],
      ['ramp', 0, 16],
    ]);
  });

  it('plays one more loop when this one is about to end', async () => {
    // 5 s into a 6 s loop: 1 s left, under the minimum.
    const { stopped } = await ending(6, 5);
    expect(stopped).toBe(22);
  });

  it('plays as many loops of a very short sound as the minimum needs', async () => {
    // 0.2 s into a 0.6 s loop: 0.4, then 1.0, 1.6 and 2.2 s.
    const { stopped, steps } = await ending(0.6, 0.2);
    expect(stopped).toBeCloseTo(10.2 + 2.2);
    expect(stopped).toBeGreaterThanOrEqual(10.2 + LAST_LOOP_MIN);
    expect(steps.at(-2)?.[2]).toBeCloseTo(12.4 - 0.2);
  });

  it('does nothing twice, nor with nothing playing', async () => {
    endLoop();
    serve(mp3());
    await loopSound('/sounds/a');
    endLoop();
    endLoop();
    expect(played()[0]?.stopped).toBe(13);
    expect(context().gains[0]?.gain.steps).toHaveLength(4);
  });

  it('a stop still fades out a loop that was ending', async () => {
    serve(mp3());
    await loopSound('/sounds/a');
    endLoop();
    stopSound();
    expect(context().gains[0]?.gain.steps.at(-1)).toEqual(['ramp', 0, 10 + STOP_FADE]);
  });
});

describe('whether a sound is heard', () => {
  it('tells the listeners when a sound starts and stops, not on every change', async () => {
    serve(mp3());
    const heard = vi.fn();
    const stop = subscribeSoundPlaying(heard);
    expect(isSoundPlaying()).toBe(false);
    await loopSound('/sounds/a');
    expect(isSoundPlaying()).toBe(true);
    // A new sound replacing the one heard is still heard: one stop and one start.
    await loopSound('/sounds/a');
    expect(heard).toHaveBeenCalledTimes(3);
    played()[1]?.dispatchEvent(new Event('ended'));
    expect(isSoundPlaying()).toBe(false);
    stop();
    await loopSound('/sounds/a');
    expect(heard).toHaveBeenCalledTimes(4);
  });

  it('gives the speaker the state as a hook', async () => {
    serve(mp3());
    const { result } = renderHook(() => useSoundPlaying());
    expect(result.current).toBe(false);
    await act(() => loopSound('/sounds/a'));
    expect(result.current).toBe(true);
    act(() => stopSound());
    expect(result.current).toBe(false);
  });
});

describe('stopping and unlocking', () => {
  it('stopping fades the sound out; with nothing playing it does nothing', async () => {
    stopSound();
    serve(mp3());
    await loopSound('/sounds/a');
    stopSound();
    stopSound();
    expect(played()[0]?.stopped).toBe(10 + STOP_FADE);
    expect(context().gains[0]?.gain.steps.at(-1)).toEqual(['ramp', 0, 10 + STOP_FADE]);
  });

  it('a sound that ended is not stopped again', async () => {
    serve(mp3());
    await loopSound('/sounds/a');
    const [source] = played();
    source?.dispatchEvent(new Event('ended'));
    stopSound();
    expect(source?.stopped).toBeNull();
    // An older sound ending does not forget the newer one.
    await loopSound('/sounds/b');
    source?.dispatchEvent(new Event('ended'));
    stopSound();
    expect(played()[1]?.stopped).toBe(10 + STOP_FADE);
  });

  it('the first tap of the visit wakes the audio, with a silent sample for older Safari', () => {
    FakeContext.startState = 'suspended';
    armAudioUnlock();
    armAudioUnlock();
    window.dispatchEvent(new Event('pointerdown'));
    expect(context().resume).toHaveBeenCalledOnce();
    expect(context().sources[0]?.started).toBe(0);
    // Once running, later taps leave it alone.
    window.dispatchEvent(new Event('keydown'));
    expect(context().resume).toHaveBeenCalledOnce();
  });

  it('a refused wake is tried again on the next tap', async () => {
    FakeContext.startState = 'suspended';
    unlockAudio();
    context().resume.mockRejectedValueOnce(new Error('not allowed'));
    context().state = 'suspended';
    unlockAudio();
    await Promise.resolve();
    expect(context().resume).toHaveBeenCalledTimes(2);
  });

  it('keeps a sound the browser holds, and plays it on the next tap', async () => {
    armAudioUnlock();
    serve(mp3());
    FakeContext.startState = 'suspended';
    FakeContext.hold = true;
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const asked = loopSound('/sounds/a');
    await vi.advanceTimersByTimeAsync(WAKE_WAIT_MS);
    await asked;
    vi.useRealTimers();
    // Not waited for forever, and nothing played yet.
    expect(played()).toHaveLength(0);

    FakeContext.hold = false;
    window.dispatchEvent(new Event('touchend'));
    await vi.waitFor(() => expect(played()).toHaveLength(1));
    expect(played()[0]?.loop).toBe(true);
    // Played once: a later tap does not start it again.
    window.dispatchEvent(new Event('pointerdown'));
    await Promise.resolve();
    expect(played()).toHaveLength(1);
  });

  it('drops a held sound when the run ends, the sound stops or is turned off before the tap', async () => {
    armAudioUnlock();
    serve(mp3());
    const hold = async (path: string) => {
      FakeContext.hold = true;
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      const asked = loopSound(path);
      await vi.advanceTimersByTimeAsync(WAKE_WAIT_MS);
      await asked;
      vi.useRealTimers();
      FakeContext.hold = false;
    };
    FakeContext.startState = 'suspended';

    await hold('/sounds/a');
    endLoop();
    window.dispatchEvent(new Event('pointerdown'));
    await Promise.resolve();
    expect(played()).toHaveLength(0);

    context().state = 'suspended';
    await hold('/sounds/b');
    stopSound();
    window.dispatchEvent(new Event('pointerdown'));
    await Promise.resolve();
    expect(played()).toHaveLength(0);

    context().state = 'suspended';
    await hold('/sounds/c');
    setSoundEnabled(false);
    window.dispatchEvent(new Event('pointerdown'));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(played()).toHaveLength(0);
  });

  it('holds a sound whose wake the browser refuses, and forgets one stopped while waking', async () => {
    armAudioUnlock();
    serve(mp3());
    FakeContext.startState = 'suspended';
    await loopSound('/sounds/a').then(
      () => undefined,
      () => undefined
    );
    // A refused wake: the sound waits for the tap instead of failing.
    context().state = 'suspended';
    context().resume.mockRejectedValueOnce(new Error('not allowed'));
    await loopSound('/sounds/b');
    expect(played()).toHaveLength(1);

    // Stopped while the context was still asked to wake: nothing waits.
    context().state = 'suspended';
    FakeContext.hold = true;
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const asked = loopSound('/sounds/c');
    stopSound();
    await vi.advanceTimersByTimeAsync(WAKE_WAIT_MS);
    await asked;
    vi.useRealTimers();
    FakeContext.hold = false;
    window.dispatchEvent(new Event('pointerdown'));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(
      context().sources.filter((source) => source.started !== null && source.loop)
    ).toHaveLength(1);
  });

  it('fades the sound out when the page is hidden', async () => {
    armAudioUnlock();
    serve(mp3());
    await loopSound('/sounds/a');
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(played()[0]?.stopped).toBeNull();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(played()[0]?.stopped).toBe(10 + STOP_FADE);
  });

  it('turning the sound off fades the playing one; turning it on wakes the audio', async () => {
    serve(mp3());
    await loopSound('/sounds/a');
    chooseSound(false);
    expect(played()[0]?.stopped).toBe(10 + STOP_FADE);
    context().state = 'suspended';
    chooseSound(true);
    expect(context().resume).toHaveBeenCalled();
  });
});
