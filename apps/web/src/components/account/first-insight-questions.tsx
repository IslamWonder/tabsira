'use client';

import { useEffect, useState } from 'react';
import {
  deviceQuestionsAsked,
  markDeviceQuestionsAsked,
  rememberDeviceAnswer,
} from '@/account/device-answers';
import { loadProfile, type ProfilePatch, patchProfile } from '@/account/profile';
import { useSession } from '@/account/session';
import { ProfileQuestions } from './profile-questions';

export interface FirstInsightQuestionsProps {
  /** How many of the three to ask (PROFILE_QUESTIONS_MAX, 0 to 3). */
  max: number;
}

type Keeper = 'account' | 'device';

/**
 * The optional questions, in the journey: after the done step on a first insight only
 * (master prompt v2 §4.7, §5). An account is asked when its profile says the
 * questions were never offered; a guest, when this device has no record of
 * them. Each answer or skip marks them asked, so a returning person finds
 * nothing to answer (§4.9). Nothing here stops the journey: the panel is
 * silent until it knows whether to ask, and absent when it should not.
 */
export function FirstInsightQuestions({ max }: FirstInsightQuestionsProps) {
  const session = useSession();
  const [keeper, setKeeper] = useState<Keeper | null>(null);

  useEffect(() => {
    if (max <= 0 || session.status === 'unknown' || session.status === 'unavailable') {
      return;
    }
    if (session.status === 'guest') {
      if (!deviceQuestionsAsked()) {
        setKeeper('device');
      }
      return;
    }
    let cancelled = false;
    void loadProfile().then((result) => {
      if (!cancelled && result.ok && !result.data.questions_asked) {
        setKeeper('account');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [max, session.status]);

  if (keeper === null) {
    return null;
  }

  const keep = async (patch: ProfilePatch): Promise<boolean> => {
    if (keeper === 'device') {
      rememberDeviceAnswer(patch);
      return true;
    }
    return (await patchProfile(patch)).ok;
  };

  const finish = () => {
    if (keeper === 'device') {
      markDeviceQuestionsAsked();
    } else {
      void patchProfile({ questions_asked: true });
    }
  };

  return <ProfileQuestions max={max} onAnswer={keep} onFinish={finish} />;
}
