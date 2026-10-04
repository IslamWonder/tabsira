import { expireCookies } from './cookies';

/**
 * Microsoft Clarity, the heatmap tool (owner decision 32). Nothing here runs
 * before the behaviour category is accepted: `<AnalyticsTags>` calls it from
 * inside a `<ConsentGate>`. Text is masked by the `data-clarity-mask`
 * attribute the layout puts on <body> (see CLARITY_MASK), so no typed text and
 * no scripture or user text is ever recorded.
 */

export const CLARITY_SCRIPT_ID = 'clarity-tag';
/** Clarity's masking attribute: the element and everything under it is masked. */
export const CLARITY_MASK = { 'data-clarity-mask': 'True' } as const;
const CLARITY_COOKIES = /^_clck$|^_clsk$|^CLID$|^ANONCHK$|^MR$|^MUID$|^SM$/;

type ClarityFunction = ((...args: unknown[]) => void) & { q?: unknown[][] };
type ClarityWindow = Window & { clarity?: ClarityFunction };

function clarityWindow(): ClarityWindow {
  return window as ClarityWindow;
}

/** Clarity's own queueing stub, so calls made before its script arrives are kept in order. */
function stub(win: ClarityWindow): ClarityFunction {
  if (win.clarity === undefined) {
    const queued: ClarityFunction = (...args: unknown[]) => {
      queued.q = [...(queued.q ?? []), args];
    };
    win.clarity = queued;
  }
  return win.clarity;
}

export function startClarity(id: string): void {
  const win = clarityWindow();
  const clarity = stub(win);
  const loaded = document.getElementById(CLARITY_SCRIPT_ID) !== null;
  // Behaviour was accepted: Clarity may keep its analytics cookies, never advertising ones.
  clarity('consentv2', { ad_Storage: 'denied', analytics_Storage: 'granted' });
  if (loaded) {
    clarity('start');
    return;
  }
  const script = document.createElement('script');
  script.id = CLARITY_SCRIPT_ID;
  script.async = true;
  script.src = `https://www.clarity.ms/tag/${encodeURIComponent(id)}`;
  document.head.appendChild(script);
}

/** A page where no tool runs (sign-in, account): the recording stops until the next page. */
export function pauseClarity(): void {
  if (document.getElementById(CLARITY_SCRIPT_ID) !== null) {
    clarityWindow().clarity?.('stop');
  }
}

/** The visitor withdrew: stop, deny storage and delete what was written. */
export function stopClarity(): void {
  const clarity = clarityWindow().clarity;
  if (clarity !== undefined) {
    clarity('consentv2', { ad_Storage: 'denied', analytics_Storage: 'denied' });
    clarity('stop');
  }
  expireCookies(CLARITY_COOKIES);
}
