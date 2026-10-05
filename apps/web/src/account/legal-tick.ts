import type { LegalVersions } from './legal';

/*
 * A tick of the terms box on the sign-up view, kept for the way back from
 * Google (owner decision 35, after the security review): never in a link,
 * only in this tab's sessionStorage, with the versions ticked and the time.
 * It is read once, and is worthless after ten minutes.
 */

const KEY = 'tabsira.legal.tick';
export const TICK_LIFETIME_MS = 10 * 60 * 1000;

export interface LegalTick {
  terms_version: string;
  privacy_version: string;
  /** The unticked-by-default full-name box of the sign-up view (decision 64). */
  public_full_name: boolean;
}

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function rememberTick(
  legal: LegalVersions,
  now: number = Date.now(),
  publicFullName = false
): void {
  storage()?.setItem(
    KEY,
    JSON.stringify({
      terms_version: legal.terms_version,
      privacy_version: legal.privacy_version,
      public_full_name: publicFullName,
      at: now,
    })
  );
}

/** The tick, once: it is removed as it is read, and only a fresh, well-formed one is returned. */
export function takeTick(now: number = Date.now()): LegalTick | null {
  const store = storage();
  const raw = store?.getItem(KEY) ?? null;
  store?.removeItem(KEY);
  if (raw === null) {
    return null;
  }
  try {
    const tick = JSON.parse(raw) as Partial<LegalTick & { at: number }>;
    const fresh =
      typeof tick.at === 'number' && now - tick.at >= 0 && now - tick.at <= TICK_LIFETIME_MS;
    if (
      fresh &&
      typeof tick.terms_version === 'string' &&
      typeof tick.privacy_version === 'string'
    ) {
      return {
        terms_version: tick.terms_version,
        privacy_version: tick.privacy_version,
        public_full_name: tick.public_full_name === true,
      };
    }
  } catch {
    // A garbled value is no tick.
  }
  return null;
}

/** Whether the tick was given to exactly the texts in force now. */
export function tickMatches(tick: LegalTick, legal: LegalVersions): boolean {
  return (
    tick.terms_version === legal.terms_version && tick.privacy_version === legal.privacy_version
  );
}
