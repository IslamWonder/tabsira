'use client';

import { useCallback, useEffect, useState } from 'react';
import { forgetLegal, type LegalVersions, loadLegal } from './legal';

export type LegalState =
  | { status: 'loading' | 'failed' }
  | { status: 'ready'; legal: LegalVersions };

/** The current versions of the terms and the privacy policy, for a form that asks to accept them. */
export function useLegal(): { state: LegalState; reload: () => void } {
  const [state, setState] = useState<LegalState>({ status: 'loading' });
  const read = useCallback(() => {
    setState({ status: 'loading' });
    void loadLegal().then((result) => {
      setState(result.ok ? { status: 'ready', legal: result.data } : { status: 'failed' });
    });
  }, []);
  useEffect(read, [read]);
  const reload = useCallback(() => {
    forgetLegal();
    read();
  }, [read]);
  return { state, reload };
}
