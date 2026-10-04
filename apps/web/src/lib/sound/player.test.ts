import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setSoundEnabled } from '@/preferences/sound';
import { chooseSound, playSound, stopSound } from './player';

class FakeAudio {
  static made: FakeAudio[] = [];
  volume = 1;
  paused = false;
  listeners = new Map<string, () => void>();
  constructor(readonly src: string) {
    FakeAudio.made.push(this);
  }
  addEventListener(name: string, listener: () => void) {
    this.listeners.set(name, listener);
  }
  play(): Promise<void> {
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
}

class RefusedAudio extends FakeAudio {
  override play(): Promise<void> {
    return Promise.reject(new DOMException('blocked', 'NotAllowedError'));
  }
}

let created = 0;
const revoked: string[] = [];

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

beforeEach(() => {
  // The player keeps the sound that is playing between tests, as it does between pages.
  stopSound();
  FakeAudio.made = [];
  revoked.length = 0;
  created = 0;
  window.localStorage.clear();
  vi.stubGlobal('Audio', FakeAudio);
  URL.createObjectURL = vi.fn(() => {
    created += 1;
    return `blob:sound-${created}`;
  });
  URL.revokeObjectURL = vi.fn((url: string) => {
    revoked.push(url);
  });
});

describe('playing the sound of an insight', () => {
  it('fetches the file from the API and plays it softly', async () => {
    const fetch = serve(mp3());
    await playSound('/sounds/ontology/E006');
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/sounds\/ontology\/E006$/));
    const [audio] = FakeAudio.made;
    expect(audio?.src).toBe('blob:sound-1');
    expect(audio?.volume).toBe(0.6);
    expect(audio?.paused).toBe(false);
  });

  it('frees the file when the sound ends', async () => {
    serve(mp3());
    await playSound('/sounds/ontology/E006');
    FakeAudio.made[0]?.listeners.get('ended')?.();
    expect(revoked).toEqual(['blob:sound-1']);
    FakeAudio.made[0]?.listeners.get('ended')?.();
    expect(revoked).toEqual(['blob:sound-1']);
  });

  it('replaces the sound that is still playing', async () => {
    serve(mp3());
    await playSound('/sounds/ontology/E006');
    await playSound('/sounds/ontology/E007');
    expect(FakeAudio.made[0]?.paused).toBe(true);
    expect(revoked).toEqual(['blob:sound-1']);
    FakeAudio.made[0]?.listeners.get('ended')?.();
    expect(revoked).toEqual(['blob:sound-1']);
  });

  it('stays quiet when the reader switched the sound off, without asking the API', async () => {
    setSoundEnabled(false);
    const fetch = serve(mp3());
    await playSound('/sounds/ontology/E006');
    expect(fetch).not.toHaveBeenCalled();
    expect(FakeAudio.made).toEqual([]);
  });

  it('stays quiet when it is switched off while the file is on its way', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        setSoundEnabled(false);
        return mp3();
      })
    );
    await playSound('/sounds/ontology/E006');
    expect(FakeAudio.made).toEqual([]);
  });

  it('ends quietly when there is no sound or no network', async () => {
    serve(new Response('{}', { status: 404 }));
    await playSound('/sounds/ontology/E999');
    serve(new TypeError('Failed to fetch'));
    await playSound('/sounds/ontology/E006');
    expect(FakeAudio.made).toEqual([]);
  });

  it('ends quietly, freeing the file, when the browser refuses to play', async () => {
    serve(mp3());
    vi.stubGlobal('Audio', RefusedAudio);
    await playSound('/sounds/ontology/E006');
    expect(revoked).toEqual(['blob:sound-1']);
  });

  it('stopping with nothing playing does nothing', () => {
    expect(() => stopSound()).not.toThrow();
  });

  it('turning the sound off stops the one that is playing; turning it on starts none', async () => {
    serve(mp3());
    await playSound('/sounds/ontology/E006');
    chooseSound(true);
    expect(FakeAudio.made[0]?.paused).toBe(false);
    chooseSound(false);
    expect(FakeAudio.made[0]?.paused).toBe(true);
    expect(window.localStorage.getItem('tabsira.sound')).toBe('off');
  });
});
