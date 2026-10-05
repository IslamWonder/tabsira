'use client';

import { MeaningSkyScene } from '@/components/progress/meaning-sky';
import { ProgressFrame, ProgressView } from '@/components/progress/progress-screen';
import { PROGRESS_EMPTY, PROGRESS_REFERENCE } from '@/test/world';

const noop = () => undefined;

/** The practice page on preview data, in one of its states: `?state=empty|loading|failed`, the reference otherwise. */
export function SkyPreview({ state }: { state?: string | undefined }) {
  if (state === 'loading' || state === 'failed') {
    return (
      <ProgressFrame>
        <MeaningSkyScene
          state={state === 'failed' ? { status: 'failed', retry: noop } : { status: 'loading' }}
        />
      </ProgressFrame>
    );
  }
  return (
    <ProgressFrame>
      <ProgressView progress={state === 'empty' ? PROGRESS_EMPTY : PROGRESS_REFERENCE} />
    </ProgressFrame>
  );
}
