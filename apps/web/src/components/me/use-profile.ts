'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type ConsentSwitch,
  loadProfile,
  type Profile,
  type ProfilePatch,
  patchProfile,
  recordConsent,
  SWITCH_FIELD,
} from '@/account/profile';
import { failureMessage } from '@/lib/api/failure-message';

export type ProfileLoad =
  | { status: 'idle' | 'loading' | 'failed' }
  | { status: 'ready'; profile: Profile };

export interface ProfileEditor {
  load: ProfileLoad;
  reload: () => void;
  /** Saves some answers; resolves to the failure's sentence, or null once saved. */
  save: (patch: ProfilePatch) => Promise<string | null>;
  /** Records a consent switch; resolves to the failure's sentence, or null once recorded. */
  setSwitch: (kind: ConsentSwitch, granted: boolean) => Promise<string | null>;
}

/**
 * The signed-in person's profile for the profile page: loaded once, and every change
 * saved at once and shown only once the API kept it (tajriba §3.5).
 */
export function useProfile(signedIn: boolean): ProfileEditor {
  const [load, setLoad] = useState<ProfileLoad>({ status: 'idle' });

  const reload = useCallback(() => {
    setLoad({ status: 'loading' });
    void loadProfile().then((result) => {
      setLoad(result.ok ? { status: 'ready', profile: result.data } : { status: 'failed' });
    });
  }, []);

  useEffect(() => {
    if (signedIn) {
      reload();
    } else {
      setLoad({ status: 'idle' });
    }
  }, [signedIn, reload]);

  // The answer shows at once; it is undone if the API refuses it. Only the
  // latest change decides what is shown, whatever order the answers arrive in.
  const latest = useRef(0);
  const shown = useRef<Profile | null>(null);
  shown.current = load.status === 'ready' ? load.profile : null;

  const save = useCallback(async (patch: ProfilePatch) => {
    // Only the sections of a loaded profile can save.
    const before = shown.current as Profile;
    const mine = ++latest.current;
    setLoad({ status: 'ready', profile: { ...before, ...patch } as Profile });
    const result = await patchProfile(patch);
    if (mine === latest.current) {
      setLoad({ status: 'ready', profile: result.ok ? result.data : before });
    }
    return result.ok ? null : failureMessage(result);
  }, []);

  const setSwitch = useCallback(async (kind: ConsentSwitch, granted: boolean) => {
    const result = await recordConsent(kind, granted);
    if (!result.ok) {
      return failureMessage(result);
    }
    // Only a loaded profile shows its switches.
    const before = shown.current as Profile;
    setLoad({ status: 'ready', profile: { ...before, [SWITCH_FIELD[kind]]: granted } });
    return null;
  }, []);

  return { load, reload, save, setSwitch };
}
