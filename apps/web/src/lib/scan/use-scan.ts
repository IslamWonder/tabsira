'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Failure, Result } from '@/lib/api/result';
import { clarifyScan, focusScan, getScan, openScanStream, type Scan } from './api';
import { type ApiStage, isTerminal, parseScanEvent, type ScanEvent } from './events';
import { followEvents, waitFor } from './follow';

export type RunStage = 'queued' | ApiStage;

export type ScanView =
  | { phase: 'loading' }
  /** The scan could not be read at all: not found, not ours, or nothing answered. */
  | { phase: 'lost'; failure: Failure }
  | { phase: 'running'; scan: Scan }
  /** The run ended: with insights, with a question, or with no reliable link. */
  | { phase: 'ready'; scan: Scan }
  | { phase: 'failed'; scan: Scan; code: string | null };

/** How long a run may take before the screen says, calmly, that it is taking longer. */
export const SLOW_AFTER_MS = 45_000;
export const POLL_EVERY_MS = 3000;

function viewOf(scan: Scan): ScanView {
  if (scan.status === 'failed') {
    return { phase: 'failed', scan, code: scan.error_code };
  }
  if (scan.status === 'done') {
    return { phase: 'ready', scan };
  }
  return { phase: 'running', scan };
}

export interface ScanControls {
  view: ScanView;
  /** The stage the server reports as running now; `queued` until the first one starts. */
  stage: RunStage;
  /** The run is taking longer than usual: say so calmly. */
  slow: boolean;
  /** A focus or an answer is on its way to the API. */
  acting: boolean;
  /** Asks again for a scan that could not be read. */
  reload: () => void;
  /** Looks again at one thing of the scene; null when accepted, else why not. */
  focus: (entityId: string) => Promise<Failure | null>;
  /** Answers the one question the scan asked; null when accepted, else why not. */
  clarify: (answer: string) => Promise<Failure | null>;
}

/**
 * Follows one scan: reads it, follows its honest stages on the event stream
 * (resuming after the last event number when the connection drops), reads it
 * again when a run ends, and falls back to asking for it every few seconds when
 * the stream cannot be kept. A late answer of an earlier run never writes over
 * the current one: events carry their run, and a scan read after a newer run
 * began is dropped.
 */
export function useScan(scanId: string): ScanControls {
  const [view, setView] = useState<ScanView>({ phase: 'loading' });
  const [acting, setActing] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [stage, setStage] = useState<RunStage>('queued');
  const [slow, setSlow] = useState(false);
  const run = useRef(0);
  const lastEventId = useRef<string | null>(null);

  const apply = useCallback((scan: Scan) => {
    // A read that is older than the run on screen is the past.
    if (scan.run < run.current) {
      return;
    }
    run.current = scan.run;
    setView(viewOf(scan));
  }, []);

  // The first read, and every «try again».
  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` is the retry trigger.
  useEffect(() => {
    const controller = new AbortController();
    setView({ phase: 'loading' });
    getScan(scanId, controller.signal).then((result) => {
      if (controller.signal.aborted) {
        return;
      }
      if (result.ok) {
        apply(result.data);
      } else {
        setView({ phase: 'lost', failure: result });
      }
    });
    return () => controller.abort();
  }, [scanId, attempt, apply]);

  const running = view.phase === 'running' ? view.scan : null;
  const streamKey = running === null ? null : `${running.id}:${running.run}`;
  const eventsUrl = running?.events_url ?? null;

  // The stream of the run on screen.
  useEffect(() => {
    if (streamKey === null || eventsUrl === null) {
      return;
    }
    const controller = new AbortController();
    const { signal } = controller;
    const thisRun = run.current;
    setStage('queued');
    setSlow(false);

    // Reads the scan again; returns it when it was read and is still ours to show.
    const reread = async (): Promise<Scan | null> => {
      const result = await getScan(scanId, signal);
      if (signal.aborted) {
        return null;
      }
      if (!result.ok) {
        setView({ phase: 'lost', failure: result });
        return null;
      }
      apply(result.data);
      return result.data;
    };

    const handle = (event: ScanEvent): boolean => {
      if (event.run < thisRun) {
        return false;
      }
      if (event.kind === 'stage') {
        if (event.state === 'started') {
          setStage(event.stage);
        } else if (event.state === 'done' && event.stage === 'understanding') {
          // The scene is understood: its photo (if it may be shown) and its things are readable now.
          void reread();
        }
      }
      return isTerminal(event);
    };

    const poll = async () => {
      while (!signal.aborted) {
        await waitFor(POLL_EVERY_MS, signal);
        if (signal.aborted) {
          return;
        }
        const result = await getScan(scanId, signal);
        if (signal.aborted) {
          return;
        }
        if (result.ok && (result.data.status === 'done' || result.data.status === 'failed')) {
          apply(result.data);
          return;
        }
        if (!result.ok && result.status !== 0) {
          setView({ phase: 'lost', failure: result });
          return;
        }
      }
    };

    void (async () => {
      const followed = await followEvents({
        open: (last, abort) => openScanStream(eventsUrl, last, abort),
        handle: (message) => {
          const event = parseScanEvent(message);
          return event === null ? false : handle(event);
        },
        signal,
        after: lastEventId.current,
      });
      lastEventId.current = followed.lastEventId;
      if (followed.end === 'aborted') {
        return;
      }
      // The run ended, or the stream could not be kept: the scan itself says where it stands.
      const scan = followed.end === 'terminal' ? await reread() : null;
      if (
        followed.end === 'gave-up' ||
        (scan !== null && scan.status !== 'done' && scan.status !== 'failed')
      ) {
        await poll();
      }
    })();

    return () => controller.abort();
  }, [streamKey, eventsUrl, scanId, apply]);

  // A run that takes longer than usual says so, once.
  useEffect(() => {
    if (streamKey === null) {
      return;
    }
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [streamKey]);

  const send = useCallback(
    async (call: Promise<Result<Scan>>): Promise<Failure | null> => {
      setActing(true);
      const result = await call;
      setActing(false);
      if (!result.ok) {
        return result;
      }
      apply(result.data);
      return null;
    },
    [apply]
  );

  return {
    view,
    stage,
    slow,
    acting,
    reload: () => setAttempt((count) => count + 1),
    focus: (entityId) => send(focusScan(scanId, entityId)),
    clarify: (answer) => send(clarifyScan(scanId, answer)),
  };
}
