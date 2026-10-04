'use client';

import { messages } from '@/messages';
import { setAmbientMotion, useAmbientMotion } from '@/preferences/motion';
import { SwitchRow } from './switch-row';

/** On or off for decorative motion, on this device (the light motes, the burst on the done button). */
export function MotionSwitch({ className }: { className?: string }) {
  const on = useAmbientMotion();
  return (
    <SwitchRow
      label={messages.preferences.motion.label}
      hint={messages.preferences.motion.hint}
      checked={on}
      onChange={setAmbientMotion}
      className={className}
    />
  );
}
