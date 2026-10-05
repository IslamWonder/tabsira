import { apiUrl } from '@/lib/scan/api';
import { readSoundEnabled, setSoundEnabled } from '@/preferences/sound';

/**
 * The insight's sound, through the Web Audio API.
 *
 * Browsers, desktop Safari first of all, refuse to start a sound that no
 * recent tap asked for, and the insight's sound arrives seconds after the tap
 * that sent the photo. One AudioContext is therefore unlocked by the first tap
 * or key anywhere on the site (`armAudioUnlock`); every later sound plays
 * through it. Each sound fades in, fades out before its end, and fades out
 * when stopped or when the page is hidden: nothing starts or ends with a click.
 */

export const VOLUME = 0.6;
/** Seconds. */
export const FADE_IN = 0.35;
export const FADE_OUT = 0.8;
export const STOP_FADE = 0.25;
const KEPT_SOUNDS = 8;

type AudioContextClass = typeof AudioContext;

let context: AudioContext | null = null;
let current: { source: AudioBufferSourceNode; gain: GainNode } | null = null;
let armed = false;
const decoded = new Map<string, AudioBuffer>();

function contextClass(): AudioContextClass | null {
  const scope = window as unknown as {
    AudioContext?: AudioContextClass;
    webkitAudioContext?: AudioContextClass;
  };
  return scope.AudioContext ?? scope.webkitAudioContext ?? null;
}

/** The page's one audio context, made on first use; null where Web Audio is missing. */
function audioContext(): AudioContext | null {
  if (context === null) {
    const Context = contextClass();
    context = Context === null ? null : new Context();
  }
  return context;
}

/** Inside a tap or a key press: wakes the audio context so later sounds may play. */
export function unlockAudio(): void {
  const audio = audioContext();
  if (audio === null || audio.state === 'running') {
    return;
  }
  void audio.resume().catch(() => {
    // Still locked: the next tap tries again.
  });
  // Older Safari unlocks only once something has played inside the gesture: one silent sample.
  const silence = audio.createBufferSource();
  silence.buffer = audio.createBuffer(1, 1, 22050);
  silence.connect(audio.destination);
  silence.start(0);
}

/** Listens for the first taps and keys of the visit, and fades the sound out when the page is hidden. */
export function armAudioUnlock(): void {
  if (armed) {
    return;
  }
  armed = true;
  for (const name of ['pointerdown', 'keydown', 'touchend'] as const) {
    window.addEventListener(name, unlockAudio, { capture: true, passive: true });
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      stopSound();
    }
  });
}

/** Fades the playing sound out and stops it; a no-op when nothing plays. */
export function stopSound(): void {
  if (current === null || context === null) {
    return;
  }
  const { source, gain } = current;
  current = null;
  const now = context.currentTime;
  gain.gain.cancelScheduledValues(now);
  gain.gain.setValueAtTime(gain.gain.value, now);
  gain.gain.linearRampToValueAtTime(0, now + STOP_FADE);
  try {
    source.stop(now + STOP_FADE);
  } catch {
    // Already stopped.
  }
}

async function bufferFor(audio: AudioContext, path: string): Promise<AudioBuffer | null> {
  const kept = decoded.get(path);
  if (kept !== undefined) {
    return kept;
  }
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    return null;
  }
  const buffer = await audio.decodeAudioData(await response.arrayBuffer());
  if (decoded.size >= KEPT_SOUNDS) {
    decoded.delete(decoded.keys().next().value as string);
  }
  decoded.set(path, buffer);
  return buffer;
}

/**
 * Plays the sound the API names, once, with its fades. A missing sound, a
 * network error, a context the browser keeps locked, or the switch turned off
 * meanwhile all end quietly: a sound is never worth an error message.
 */
export async function playSound(path: string): Promise<void> {
  if (!readSoundEnabled()) {
    return;
  }
  stopSound();
  const audio = audioContext();
  if (audio === null) {
    return;
  }
  try {
    if (audio.state !== 'running') {
      await audio.resume();
    }
    const buffer = await bufferFor(audio, path);
    if (buffer === null || !readSoundEnabled() || audio.state !== 'running') {
      return;
    }
    stopSound();
    const source = audio.createBufferSource();
    const gain = audio.createGain();
    source.buffer = buffer;
    source.connect(gain);
    gain.connect(audio.destination);

    const start = audio.currentTime;
    const end = start + buffer.duration;
    const fadeIn = Math.min(FADE_IN, buffer.duration / 3);
    const fadeOut = Math.min(FADE_OUT, buffer.duration / 3);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(VOLUME, start + fadeIn);
    gain.gain.setValueAtTime(VOLUME, end - fadeOut);
    gain.gain.linearRampToValueAtTime(0, end);

    current = { source, gain };
    source.addEventListener('ended', () => {
      if (current?.source === source) {
        current = null;
      }
    });
    source.start(start);
  } catch {
    stopSound();
  }
}

/** The reader's choice: remembered on this device, and a sound already playing fades out at once. */
export function chooseSound(on: boolean): void {
  setSoundEnabled(on);
  if (on) {
    unlockAudio();
  } else {
    stopSound();
  }
}

/** For tests: forget the context, the sounds and the listeners' guard. */
export function resetAudio(): void {
  context = null;
  current = null;
  armed = false;
  decoded.clear();
}
