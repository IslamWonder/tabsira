import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setSoundEnabled } from '@/preferences/sound';
import {
  armAudioUnlock,
  chooseSound,
  FADE_IN,
  FADE_OUT,
  playSound,
  resetAudio,
  STOP_FADE,
  stopSound,
  unlockAudio,
  VOLUME,
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
  state: AudioContextState = FakeContext.startState;
  currentTime = 10;
  destination = {};
  sources: FakeSource[] = [];
  gains: { gain: FakeParam; connect: ReturnType<typeof vi.fn> }[] = [];
  decodeAudioData = vi.fn(async () => ({ duration: 3 }));
  resume = vi.fn(async () => {
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
  window.localStorage.clear();
  vi.stubGlobal('AudioContext', FakeContext);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('playSound', () => {
  it('fetches the file once, plays it with a fade in and a fade out before its end', async () => {
    const fetch = serve(mp3());
    await playSound('/sounds/ontology/E006');

    expect(fetch).toHaveBeenCalledOnce();
    const [source] = played();
    expect(source?.started).toBe(10);
    expect(context().gains[0]?.gain.steps).toEqual([
      ['set', 0, 10],
      ['ramp', VOLUME, 10 + FADE_IN],
      ['set', VOLUME, 13 - FADE_OUT],
      ['ramp', 0, 13],
    ]);
    source?.dispatchEvent(new Event('ended'));
    // Played again from memory: no second download.
    await playSound('/sounds/ontology/E006');
    expect(fetch).toHaveBeenCalledOnce();
    expect(played()).toHaveLength(2);
  });

  it('keeps the fades inside a very short sound', async () => {
    serve(mp3());
    await playSound('/sounds/a');
    context().decodeAudioData.mockResolvedValueOnce({ duration: 0.3 });
    await playSound('/sounds/b');
    const steps = context().gains[1]?.gain.steps ?? [];
    expect(steps[1]).toEqual(['ramp', VOLUME, 10.1]);
    expect(steps[2]?.[2]).toBeCloseTo(10.2);
  });

  it('fades out the sound still playing when another starts', async () => {
    serve(mp3());
    await playSound('/sounds/a');
    await playSound('/sounds/b');
    const [first, second] = played();
    expect(first?.stopped).toBe(10 + STOP_FADE);
    expect(second?.stopped).toBeNull();
  });

  it('wakes a sleeping context, and stays quiet when the browser keeps it locked', async () => {
    serve(mp3());
    FakeContext.startState = 'suspended';
    await playSound('/sounds/a');
    expect(context().resume).toHaveBeenCalled();
    expect(played()).toHaveLength(1);

    resetAudio();
    FakeContext.made = [];
    FakeContext.startState = 'suspended';
    await playSound('/sounds/a');
    context().resume.mockImplementation(async () => {});
    context().state = 'suspended';
    await playSound('/sounds/b');
    expect(context().sources.filter((s) => s.started !== null)).toHaveLength(1);
  });

  it('stays quiet when switched off, before or while the file comes', async () => {
    const fetch = serve(mp3());
    setSoundEnabled(false);
    await playSound('/sounds/a');
    expect(fetch).not.toHaveBeenCalled();

    setSoundEnabled(true);
    fetch.mockImplementationOnce(async () => {
      setSoundEnabled(false);
      return mp3();
    });
    await playSound('/sounds/b');
    expect(played()).toHaveLength(0);
  });

  it('ends quietly with no sound, no network, a bad file or no Web Audio', async () => {
    serve(new Response('', { status: 404 }));
    await playSound('/sounds/missing');
    serve(new TypeError('offline'));
    await playSound('/sounds/a');
    serve(mp3());
    context().decodeAudioData.mockRejectedValueOnce(new Error('not audio'));
    await playSound('/sounds/b');
    expect(played()).toHaveLength(0);

    resetAudio();
    vi.stubGlobal('AudioContext', undefined);
    await expect(playSound('/sounds/a')).resolves.toBeUndefined();
    expect(() => unlockAudio()).not.toThrow();
  });

  it('forgets the oldest decoded sound once it holds eight', async () => {
    const fetch = serve(mp3());
    for (let n = 0; n < 9; n += 1) {
      await playSound(`/sounds/${n}`);
    }
    await playSound('/sounds/0');
    expect(fetch).toHaveBeenCalledTimes(10);
  });
});

describe('stopping and unlocking', () => {
  it('stopping fades the sound out; with nothing playing it does nothing', async () => {
    stopSound();
    serve(mp3());
    await playSound('/sounds/a');
    stopSound();
    stopSound();
    expect(played()[0]?.stopped).toBe(10 + STOP_FADE);
    expect(context().gains[0]?.gain.steps.at(-1)).toEqual(['ramp', 0, 10 + STOP_FADE]);
  });

  it('a sound that ended is not stopped again', async () => {
    serve(mp3());
    await playSound('/sounds/a');
    const [source] = played();
    source?.dispatchEvent(new Event('ended'));
    stopSound();
    expect(source?.stopped).toBeNull();
    // An older sound ending does not forget the newer one.
    await playSound('/sounds/b');
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

  it('fades the sound out when the page is hidden', async () => {
    armAudioUnlock();
    serve(mp3());
    await playSound('/sounds/a');
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(played()[0]?.stopped).toBeNull();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(played()[0]?.stopped).toBe(10 + STOP_FADE);
  });

  it('turning the sound off fades the playing one; turning it on wakes the audio', async () => {
    serve(mp3());
    await playSound('/sounds/a');
    chooseSound(false);
    expect(played()[0]?.stopped).toBe(10 + STOP_FADE);
    context().state = 'suspended';
    chooseSound(true);
    expect(context().resume).toHaveBeenCalled();
  });
});
