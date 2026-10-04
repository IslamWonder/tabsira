import { apiUrl } from '@/lib/scan/api';
import { readSoundEnabled, setSoundEnabled } from '@/preferences/sound';

const VOLUME = 0.6;

let current: { audio: HTMLAudioElement; url: string } | null = null;

/** Stops the sound that is playing, if any, and frees its memory. */
export function stopSound(): void {
  if (current === null) {
    return;
  }
  const { audio, url } = current;
  current = null;
  audio.pause();
  URL.revokeObjectURL(url);
}

/**
 * Plays the sound the API names, once. The file is fetched by the page itself
 * and played from memory, so the page needs no new origin for media. A sound
 * that is missing, a network error, a browser that refuses to play before a
 * tap, or the switch turned off meanwhile all end quietly: a sound is never
 * worth an error message.
 */
export async function playSound(path: string): Promise<void> {
  if (!readSoundEnabled()) {
    return;
  }
  stopSound();
  try {
    const response = await fetch(apiUrl(path));
    if (!response.ok || !readSoundEnabled()) {
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const audio = new Audio(url);
    audio.volume = VOLUME;
    stopSound();
    current = { audio, url };
    audio.addEventListener('ended', () => {
      if (current?.audio === audio) {
        stopSound();
      }
    });
    await audio.play();
  } catch {
    stopSound();
  }
}

/** The reader's choice: remembered on this device, and a sound already playing stops at once. */
export function chooseSound(on: boolean): void {
  setSoundEnabled(on);
  if (!on) {
    stopSound();
  }
}
