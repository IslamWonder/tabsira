import { readConsent } from '@/consent/store';
import { isExcludedPath } from './paths';

/**
 * The product's own events, as GA4 receives them. The parameter types are the
 * contract (owner decision 28): only fixed words, counts and booleans, never a
 * name, an id of a person, free text, scripture, a location or a photo. A new
 * event is a new line here, reviewed with the privacy text.
 */
export interface AnalyticsEvents {
  scan_started: { source: 'camera' | 'upload' | 'example' };
  scan_finished: { outcome: 'insight' | 'none' | 'failed'; seconds: number };
  insight_opened: { origin: 'scene' | 'world' | 'community' | 'atlas' | 'link' };
  /** «تمّ» pressed on an insight. */
  done_pressed: { context: 'insight' };
  share: { method: 'link' | 'card' | 'system'; kind: 'insight' | 'place' | 'post' };
  sign_up_completed: { method: 'email' | 'google' };
  /** Sent only while analytics stays allowed: a withdrawal cannot be reported to the tool it stopped. */
  consent_changed: { analytics: boolean; behaviour: boolean };
}

export type EventName = keyof AnalyticsEvents;
type Parameters = Record<string, string | number | boolean>;
type GtagFunction = (...args: unknown[]) => void;

interface Queued {
  name: EventName;
  params: Parameters;
}

const WORD = /^[a-z0-9_]{1,40}$/;
const QUEUE_LIMIT = 10;
/** Events of a page where no tool runs (sign-up), kept in memory until the next page that allows one. */
let queue: Queued[] = [];

/** Defence in depth beside the types: a string that is not a short fixed word is dropped. */
function cleanParams(params: Readonly<Record<string, unknown>>): Parameters {
  const clean: Parameters = {};
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) {
      clean[key] = value;
    } else if (typeof value === 'string' && WORD.test(value)) {
      clean[key] = value;
    }
  }
  return clean;
}

function gtagOf(): GtagFunction | null {
  const gtag = (window as { gtag?: GtagFunction }).gtag;
  return typeof gtag === 'function' ? gtag : null;
}

function analyticsAllowed(): boolean {
  const { consent } = readConsent();
  return consent.status === 'decided' && consent.record.categories.analytics && gtagOf() !== null;
}

/** Reports one event, only while the analytics category is accepted; otherwise nothing leaves the page. */
export function track<N extends EventName>(name: N, params: AnalyticsEvents[N]): void {
  if (!analyticsAllowed()) {
    return;
  }
  const event: Queued = { name, params: cleanParams(params) };
  if (isExcludedPath(window.location.pathname)) {
    queue = [...queue, event].slice(-QUEUE_LIMIT);
    return;
  }
  gtagOf()?.('event', event.name, event.params);
}

/** On the first page that allows analytics after the event happened. */
export function flushEvents(): void {
  if (!analyticsAllowed() || isExcludedPath(window.location.pathname)) {
    return;
  }
  const waiting = queue;
  queue = [];
  for (const event of waiting) {
    gtagOf()?.('event', event.name, event.params);
  }
}

export function dropQueuedEvents(): void {
  queue = [];
}
