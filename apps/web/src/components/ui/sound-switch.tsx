'use client';

import { chooseSound } from '@/lib/sound/player';
import { messages } from '@/messages';
import { useSoundEnabled } from '@/preferences/sound';
import { SwitchRow } from './switch-row';

/** On or off for the sound effect of an opened insight, on this device (the profile page). */
export function SoundSwitch({ className }: Readonly<{ className?: string }>) {
  const on = useSoundEnabled();
  return (
    <SwitchRow
      label={messages.preferences.sound.label}
      hint={messages.preferences.sound.hint}
      checked={on}
      onChange={chooseSound}
      className={className}
    />
  );
}
