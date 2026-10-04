'use client';

import { SoundOffIcon, SoundOnIcon } from '@/components/icons';
import { chooseSound } from '@/lib/sound/player';
import { messages } from '@/messages';
import { useSoundEnabled } from '@/preferences/sound';
import { Button } from './button';

/**
 * The one-tap sound switch: a speaker, with a cross when the sound is off.
 * It is a toggle button, so its name does not change and assistive
 * technology reads the state from aria-pressed; hovering shows the state.
 */
export function SoundToggle({ className }: { className?: string }) {
  const on = useSoundEnabled();
  const Icon = on ? SoundOnIcon : SoundOffIcon;
  return (
    <Button
      variant="icon"
      label={messages.sound.toggle}
      title={messages.sound.state(on ? messages.sound.on : messages.sound.off)}
      aria-pressed={on}
      onClick={() => chooseSound(!on)}
      className={className}
    >
      <Icon width="20" height="20" />
    </Button>
  );
}
