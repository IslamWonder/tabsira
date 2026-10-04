'use client';

import { messages } from '@/messages';
import { rememberAmbientMotion } from '@/preferences/account-sync';
import { setAmbientMotion, useAmbientMotion } from '@/preferences/motion';
import { SwitchRow } from './switch-row';

/** On or off for decorative motion, on this device and in the account when signed in (the light motes, the burst on the done button). */
export function MotionSwitch({ className }: { className?: string }) {
  const on = useAmbientMotion();
  return (
    <SwitchRow
      label={messages.preferences.motion.label}
      hint={messages.preferences.motion.hint}
      checked={on}
      onChange={(next) => {
        setAmbientMotion(next);
        void rememberAmbientMotion(next);
      }}
      className={className}
    />
  );
}
