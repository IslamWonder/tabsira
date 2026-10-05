'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { markProfileRequired } from '@/account/session';
import { RAIN_PHOTO } from '@/components/scene/rain-scene';
import type { Failure } from '@/lib/api/result';
import {
  type ActionChoice,
  apiUrl,
  askInsight,
  type Completion,
  completeInsight,
  declareAction,
  getInsight,
  getProgress,
  getScan,
  type Insight,
  type Progress,
} from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { profileRequired } from '@/lib/scan/gate';
import type { StepStatus } from './step-card';

export type InsightLoad =
  | { phase: 'loading' }
  | { phase: 'lost'; failure: Failure }
  | { phase: 'ready'; insight: Insight };

/** What stands where the photo would: the photo, or the reason there is none. */
export type PhotoView =
  | { kind: 'photo'; src: string; width: number; height: number; unoptimized: boolean }
  | { kind: 'sensitive' }
  | { kind: 'gone' }
  | { kind: 'none' };

export interface StepState {
  status: StepStatus;
  /** What the API says the recorded answer means. */
  means?: string;
  error?: string;
}

export interface FinishState {
  status: 'idle' | 'saving' | 'done';
  error?: string;
  /** What the done action returned, only in the visit that completed it. */
  completion: Completion | null;
  progress: Progress | null;
  progressFailed: boolean;
}

export interface InsightControls {
  load: InsightLoad;
  /** Null until it is known whether a photo may be shown. */
  photo: PhotoView | null;
  step: StepState;
  finish: FinishState;
  reload: () => void;
  declare: (choice: ActionChoice) => Promise<void>;
  complete: () => Promise<void>;
  ask: (message: string, key: string) => Promise<Failure | null>;
}

const GONE: PhotoView = { kind: 'gone' };
const NONE: PhotoView = { kind: 'none' };

function stepOf(insight: Insight): StepState {
  const { state, means } = insight.action;
  const status: StepStatus = state === 'done' ? 'saved' : state === 'later' ? 'deferred' : 'idle';
  return means === null ? { status } : { status, means };
}

const IDLE_FINISH: FinishState = {
  status: 'idle',
  completion: null,
  progress: null,
  progressFailed: false,
};

function finishOf(insight: Insight): FinishState {
  return insight.completed_at === null ? IDLE_FINISH : { ...IDLE_FINISH, status: 'done' };
}

/** Where the photo of an insight comes from: the prepared rain photo, or the scan's, while it is kept. */
async function photoOf(insight: Insight): Promise<PhotoView> {
  if (insight.origin === 'tutorial') {
    return { kind: 'photo', ...RAIN_PHOTO, unoptimized: false };
  }
  if (insight.image.sensitive) {
    return { kind: 'sensitive' };
  }
  if (insight.scan_id === null || insight.image.url === null) {
    return NONE;
  }
  const scan = await getScan(insight.scan_id);
  if (!scan.ok) {
    return NONE;
  }
  const { image } = scan.data;
  if (!image.available || image.url === null || image.width === null || image.height === null) {
    return GONE;
  }
  return {
    kind: 'photo',
    src: apiUrl(image.url),
    width: image.width,
    height: image.height,
    // A private photo is fetched with the visitor's session; the optimiser has no session.
    unoptimized: true,
  };
}

/**
 * Everything an insight page does with the API: read the insight and its
 * photo, record the small step, ask in the chat, and complete it. Each write
 * guards against a second tap while one is on its way, and none announces
 * success before the API has answered (tajriba §3.5).
 */
export function useInsight(insightId: string): InsightControls {
  const [insight, setInsight] = useState<Insight | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [photo, setPhoto] = useState<PhotoView | null>(null);
  const [step, setStep] = useState<StepState>({ status: 'idle' });
  const [finish, setFinish] = useState<FinishState>(IDLE_FINISH);
  const [attempt, setAttempt] = useState(0);
  const stepBusy = useRef(false);
  const finishBusy = useRef(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` is the retry trigger.
  useEffect(() => {
    const controller = new AbortController();
    setInsight(null);
    setFailure(null);
    setPhoto(null);
    getInsight(insightId, controller.signal).then(async (result) => {
      if (controller.signal.aborted) {
        return;
      }
      if (!result.ok) {
        setFailure(result);
        return;
      }
      setStep(stepOf(result.data));
      setFinish(finishOf(result.data));
      setInsight(result.data);
      const view = await photoOf(result.data);
      if (!controller.signal.aborted) {
        setPhoto(view);
      }
    });
    return () => controller.abort();
  }, [insightId, attempt]);

  const declare = useCallback(
    async (choice: ActionChoice) => {
      if (stepBusy.current) {
        return;
      }
      stepBusy.current = true;
      const before = step;
      setStep({ status: 'saving' });
      const result = await declareAction(insightId, choice);
      stepBusy.current = false;
      if (!result.ok) {
        setStep({ ...before, error: journeyFailureMessage(result) });
        return;
      }
      const means = result.data.means ?? undefined;
      setStep({ status: result.data.state === 'done' ? 'saved' : 'deferred', means });
    },
    [insightId, step]
  );

  const complete = useCallback(async () => {
    if (finishBusy.current) {
      return;
    }
    finishBusy.current = true;
    setFinish((current) => ({ ...current, status: 'saving', error: undefined }));
    const result = await completeInsight(insightId);
    if (!result.ok) {
      finishBusy.current = false;
      setFinish((current) => ({
        ...current,
        status: 'idle',
        error: journeyFailureMessage(result),
      }));
      return;
    }
    setFinish({ status: 'done', completion: result.data, progress: null, progressFailed: false });
    if (result.data.first_time) {
      const progress = await getProgress(Intl.DateTimeFormat().resolvedOptions().timeZone);
      setFinish((current) =>
        progress.ok ? { ...current, progress: progress.data } : { ...current, progressFailed: true }
      );
    }
  }, [insightId]);

  const ask = useCallback(
    async (message: string, key: string): Promise<Failure | null> => {
      const result = await askInsight(insightId, message, key);
      if (!result.ok) {
        if (profileRequired(result)) {
          // The profile form opens before anything else (decision 64).
          markProfileRequired();
        }
        return result;
      }
      const { used, limit, remaining, message: reply } = result.data;
      // A question can only be asked from a page that has its insight.
      setInsight((current) => {
        const { chat } = current as Insight;
        return {
          ...(current as Insight),
          chat: { ...chat, used, limit, remaining, messages: [...chat.messages, reply] },
        };
      });
      return null;
    },
    [insightId]
  );

  let load: InsightLoad = { phase: 'loading' };
  if (insight !== null) {
    load = { phase: 'ready', insight };
  } else if (failure !== null) {
    load = { phase: 'lost', failure };
  }

  return {
    load,
    photo,
    step,
    finish,
    reload: () => setAttempt((count) => count + 1),
    declare,
    complete,
    ask,
  };
}
