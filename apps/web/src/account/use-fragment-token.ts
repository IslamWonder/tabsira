'use client';

import { useEffect, useRef, useState } from 'react';
import { fragmentToken } from './links';

export type FragmentToken =
  | { status: 'reading' }
  | { status: 'missing' }
  | { status: 'found'; token: string };

function takeToken(): FragmentToken {
  const token = fragmentToken(window.location.hash);
  if (token === null) {
    return { status: 'missing' };
  }
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${window.location.search}`
  );
  return { status: 'found', token };
}

/**
 * The token of a mailed link, read once from `#token=` (docs/AUTH.md), then
 * taken out of the address bar: kept in memory only, it does not linger in
 * the history, a bookmark or a screenshot. The server render cannot see a
 * fragment, so the first render is `reading`. The ref keeps the token when
 * React runs the effect twice in development.
 */
export function useFragmentToken(): FragmentToken {
  const taken = useRef<FragmentToken | null>(null);
  const [state, setState] = useState<FragmentToken>({ status: 'reading' });
  useEffect(() => {
    taken.current ??= takeToken();
    setState(taken.current);
  }, []);
  return state;
}
