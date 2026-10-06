import { useSyncExternalStore } from 'react';
import { apiUrl } from '@/lib/scan/api';
import { readSoundEnabled, setSoundEnabled } from '@/preferences/sound';

/**
 * The scene's sound, through the Web Audio API.
 *
 * Browsers, desktop Safari first of all, refuse to start a sound that no
 * recent tap asked for, and the scene's sound arrives seconds after the tap
 * that sent the photo. One AudioContext is therefore unlocked by the first tap
 * or key anywhere on the site (`armAudioUnlock`); every later sound plays
 * through it. The sound loops while the insight is prepared and ends on the
 * end of a loop (`endLoop`), never in the middle of one. It fades in, fades
 * out before it ends, and fades out when stopped or when the page is hidden:
 * nothing starts or ends with a click.
 *
 * A phone hides the page while its camera or its photo picker is open, and the
 * browser then holds the audio (iOS «interrupts» the context) until the next
 * tap. A sound that arrives while the audio is held is therefore not lost: it
 * waits, and the next tap or key anywhere on the page starts it, unless the run
 * ended or the sound was turned off meanwhile. A wake that the browser leaves
 * unanswered is never awaited for more than WAKE_WAIT_MS.
 */

export const VOLUME = 0.6;
/** Seconds. */
export const FADE_IN = 0.35;
export const FADE_OUT = 0.8;
export const STOP_FADE = 0.25;
/** Seconds: a loop that would end sooner than this once the scan ends is played once more. */
export const LAST_LOOP_MIN = 2;
const KEPT_SOUNDS = 8;
/** Milliseconds a sleeping context may take to wake before its sound waits for the next tap. */
export const WAKE_WAIT_MS = 400;

type AudioContextClass = typeof AudioContext;

let context: AudioContext | null = null;
interface Playing {
  source: AudioBufferSourceNode;
  gain: GainNode;
  /** When the first loop began, on the context's clock. */
  start: number;
  duration: number;
  ending: boolean;
}

let current: Playing | null = null;
const listeners = new Set<() => void>();

/**
 * Sets the playing sound and tells the speakers on screen, which show it
 * while it is heard. Every call is a change: a sound starts only once the
 * one before it was stopped.
 */
function setCurrent(next: Playing | null): void {
  current = next;
  for (const listener of listeners) {
    listener();
  }
}

/** True while a sound is heard, fade out included until its stop is asked. */
export function isSoundPlaying(): boolean {
  return current !== null;
}

/** Calls `onChange` when a sound starts or stops being heard. */
export function subscribeSoundPlaying(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

function notPlaying(): boolean {
  return false;
}

/** Whether the scene's sound is heard now, for the speaker that shows it. */
export function useSoundPlaying(): boolean {
  return useSyncExternalStore(subscribeSoundPlaying, isSoundPlaying, notPlaying);
}
// Grows with every stop: a sound still downloading when it was stopped never starts.
let generation = 0;
let armed = false;
const decoded = new Map<string, AudioBuffer>();
/** A sound the browser would not let start yet, and the run it belongs to. */
let pending: { path: string; generation: number } | null = null;

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

/**
 * Inside a tap or a key press: wakes the audio context so later sounds may play,
 * and starts the sound that was waiting for this tap, if its run still asks for it.
 */
export function unlockAudio(): void {
  const audio = audioContext();
  if (audio === null) {
    return;
  }
  const waiting = pending;
  pending = null;
  if (audio.state !== 'running') {
    void audio.resume().catch(() => {
      // Still locked: the next tap tries again.
    });
    // Older Safari unlocks only once something has played inside the gesture: one silent sample.
    const silence = audio.createBufferSource();
    silence.buffer = audio.createBuffer(1, 1, 22050);
    silence.connect(audio.destination);
    silence.start(0);
  }
  if (waiting !== null && waiting.generation === generation) {
    void loopSound(waiting.path);
  }
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
  generation += 1;
  pending = null;
  if (current === null || context === null) {
    return;
  }
  const { source, gain } = current;
  setCurrent(null);
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

/** Asks a sleeping context to wake, for WAKE_WAIT_MS at most; true when it runs. */
async function wake(audio: AudioContext): Promise<boolean> {
  if (audio.state === 'running') {
    return true;
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, WAKE_WAIT_MS);
  });
  await Promise.race([audio.resume().catch(() => undefined), late]);
  clearTimeout(timer);
  return (audio.state as AudioContextState) === 'running';
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
 * Loops the sound the API names, with a fade in, until `endLoop` or
 * `stopSound`. A missing sound, a network error, a context the browser keeps
 * locked, the switch turned off, or a stop asked for while the file came all
 * end quietly: a sound is never worth an error message.
 */
export async function loopSound(path: string): Promise<void> {
  if (!readSoundEnabled()) {
    return;
  }
  stopSound();
  const asked = generation;
  const audio = audioContext();
  if (audio === null) {
    return;
  }
  try {
    if (!(await wake(audio))) {
      // Held by the browser (the page was hidden by the camera, or no tap yet): the next tap plays it.
      if (asked === generation) {
        pending = { path, generation: asked };
      }
      return;
    }
    const buffer = await bufferFor(audio, path);
    if (
      buffer === null ||
      asked !== generation ||
      !readSoundEnabled() ||
      audio.state !== 'running'
    ) {
      return;
    }
    const source = audio.createBufferSource();
    const gain = audio.createGain();
    source.buffer = buffer;
    source.loop = true;
    source.connect(gain);
    gain.connect(audio.destination);

    const start = audio.currentTime;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(VOLUME, start + Math.min(FADE_IN, buffer.duration / 3));

    const playing: Playing = { source, gain, start, duration: buffer.duration, ending: false };
    setCurrent(playing);
    source.addEventListener('ended', () => {
      if (current === playing) {
        setCurrent(null);
      }
    });
    source.start(start);
  } catch {
    stopSound();
  }
}

/**
 * The insight is ready: the looping sound ends with the loop it is playing,
 * or with the next one when this one would end in under LAST_LOOP_MIN
 * seconds, fading out before that end. A sound still downloading never starts.
 */
export function endLoop(): void {
  generation += 1;
  pending = null;
  if (current === null || context === null || current.ending) {
    return;
  }
  const { source, gain, start, duration } = current;
  current.ending = true;
  const now = context.currentTime;
  let left = duration - ((now - start) % duration);
  while (left < LAST_LOOP_MIN) {
    left += duration;
  }
  const end = now + left;
  gain.gain.setValueAtTime(VOLUME, end - Math.min(FADE_OUT, duration / 3));
  gain.gain.linearRampToValueAtTime(0, end);
  source.stop(end);
}

/** The call to act: a soft rising fifth, drawn on the spot, so no file is fetched. Hz. */
export const CHIME_NOTES = [659.25, 987.77] as const;
/** Seconds between the two notes, and how long each rings. */
export const CHIME_GAP = 0.14;
export const CHIME_RING = 1.1;
export const CHIME_VOLUME = 0.22;
const CHIME_ATTACK = 0.02;

/**
 * A short call when the scan needs the reader. It is heard only when the
 * switch is on and the audio already runs; unlike the scene's sound it never
 * waits for a tap, since a call heard late would point at nothing.
 */
export function playChime(): void {
  const audio = context;
  if (!readSoundEnabled() || audio?.state !== 'running') {
    return;
  }
  const now = audio.currentTime;
  CHIME_NOTES.forEach((frequency, index) => {
    const start = now + index * CHIME_GAP;
    const tone = audio.createOscillator();
    const gain = audio.createGain();
    tone.type = 'sine';
    tone.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(CHIME_VOLUME, start + CHIME_ATTACK);
    gain.gain.linearRampToValueAtTime(0, start + CHIME_RING);
    tone.connect(gain);
    gain.connect(audio.destination);
    tone.start(start);
    tone.stop(start + CHIME_RING);
  });
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
  generation = 0;
  armed = false;
  pending = null;
  decoded.clear();
}
