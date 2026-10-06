'use client';

import { SoundOffIcon, SoundOnIcon, SoundPlayingIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { chooseSound, useSoundPlaying } from '@/lib/sound/player';
import { messages } from '@/messages';
import { useSoundEnabled } from '@/preferences/sound';
import { Button } from './button';

/**
 * The one-tap sound switch: a speaker, with a cross when the sound is off.
 * It is a toggle button, so its name does not change and assistive
 * technology reads the state from aria-pressed; hovering shows the state.
 * While the scene's sound is heard, the speaker's waves become three bars
 * that rise and fall and a gold ring breathes around it, so the reader sees
 * where the sound comes from and how to stop it. Under reduced motion the
 * bars and the ring stay still, and the title still says it is playing.
 *
 * `className` places the switch (an absolute corner of a photo); without
 * one it sits in the flow.
 */
export function SoundToggle({ className }: Readonly<{ className?: string }>) {
  const on = useSoundEnabled();
  const playing = useSoundPlaying() && on;
  const IdleIcon = on ? SoundOnIcon : SoundOffIcon;
  const Icon = playing ? SoundPlayingIcon : IdleIcon;
  const idleState = on ? messages.sound.on : messages.sound.off;
  const state = playing ? messages.sound.playing : idleState;
  return (
    <span className={cx('inline-flex rounded-full', className ?? 'relative')}>
      {playing ? (
        <span
          aria-hidden="true"
          data-testid="sound-ring"
          className="fx-sound-ring pointer-events-none absolute inset-0 rounded-full"
        />
      ) : null}
      <Button
        variant="icon"
        label={messages.sound.toggle}
        title={messages.sound.state(state)}
        aria-pressed={on}
        onClick={() => chooseSound(!on)}
      >
        <Icon width="20" height="20" />
      </Button>
    </span>
  );
}
