'use client';

import { useCallback, useState } from 'react';
import { CheckIcon } from '@/components/icons';
import { Notice } from '@/components/ui/notice';
import { messages } from '@/messages';

export type SaveState = { kind: 'idle' | 'saving' | 'saved' } | { kind: 'failed'; message: string };

/** Runs a save and remembers how it went, for the line under a group of settings. */
export function useSaveState() {
  const [state, setState] = useState<SaveState>({ kind: 'idle' });
  const run = useCallback(async (save: () => Promise<string | null>) => {
    setState({ kind: 'saving' });
    const problem = await save();
    setState(problem === null ? { kind: 'saved' } : { kind: 'failed', message: problem });
    return problem === null;
  }, []);
  return { state, run, busy: state.kind === 'saving' };
}

/**
 * «saving» while a change travels, «saved» once the API kept it, or what went
 * wrong and what to do (tajriba §3.5). Always present, so it is announced.
 */
export function SaveStatus({ state }: { state: SaveState }) {
  return (
    <>
      <p role="status" className="m-0 flex min-h-6 items-center gap-1.5 text-fg-soft text-sm">
        {state.kind === 'saving' ? messages.profile.saving : null}
        {state.kind === 'saved' ? (
          <>
            <CheckIcon width="16" height="16" className="text-primary" />
            {messages.settings.saved}
          </>
        ) : null}
      </p>
      {state.kind === 'failed' ? (
        <div role="alert">
          <Notice tone="error">{state.message}</Notice>
        </div>
      ) : null}
    </>
  );
}
