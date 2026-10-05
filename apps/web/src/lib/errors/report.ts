import { apiUrl } from '@/lib/scan/api';

/**
 * The browser's errors, sent to the API's `POST /client-errors`, which cleans
 * them and forwards them to GlitchTip (docs/ERROR_TRACKING.md §7). The bundle
 * carries no DSN and the browser talks to nobody but the API. A report holds
 * the error's type, message and stack and the page address without its query
 * or fragment; nothing is kept on the device and no cookie is sent. Reporting
 * never throws and never reports itself.
 */

export const FLUSH_DELAY_MS = 2000;
/** The API's own bounds (`ClientReportBatch`). */
export const MAX_BATCH = 10;
const MAX_MESSAGE = 2000;
const MAX_STACK = 16_000;
/** At most this many reports a page load: a loop of errors must not flood the API. */
export const MAX_PER_PAGE = 20;
const IDENTIFIER = /^[A-Za-z0-9_.$-]{1,100}$/;

interface ClientReport {
  kind: 'error';
  level: 'error' | 'fatal';
  message: string;
  name?: string;
  stack?: string;
  url: string;
  handled: boolean;
}

let queue: ClientReport[] = [];
let sent = 0;
const seen = new Set<string>();
let timer: ReturnType<typeof setTimeout> | null = null;
let installed = false;

/** The page address without its query string or fragment, which may carry ids or tokens. */
function pageAddress(): string {
  return `${window.location.origin}${window.location.pathname}`;
}

function toReport(error: unknown, handled: boolean): ClientReport {
  const isError = error instanceof Error;
  const raw = isError ? error.message : typeof error === 'string' ? error : '';
  const message = (raw || (isError ? error.name : '') || 'Unknown error').slice(0, MAX_MESSAGE);
  const report: ClientReport = {
    kind: 'error',
    level: handled ? 'error' : 'fatal',
    message,
    url: pageAddress(),
    handled,
  };
  if (isError && IDENTIFIER.test(error.name)) {
    report.name = error.name;
  }
  if (isError && typeof error.stack === 'string' && error.stack !== '') {
    report.stack = error.stack.slice(0, MAX_STACK);
  }
  return report;
}

/** Sends what is queued, at most a batch at a time; a failure is dropped quietly. */
export function flushErrors(): void {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
  while (queue.length > 0) {
    const items = queue.slice(0, MAX_BATCH);
    queue = queue.slice(MAX_BATCH);
    try {
      void fetch(apiUrl('/client-errors'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
        // Survives the page being closed; no cookie: a report names nobody.
        keepalive: true,
        credentials: 'omit',
      }).catch(() => undefined);
    } catch {
      // No network API at all: nothing to do.
    }
  }
}

/** Queues one error for the API; the same error twice in a page load is sent once. */
export function reportError(error: unknown, { handled = true }: { handled?: boolean } = {}): void {
  if (sent >= MAX_PER_PAGE) {
    return;
  }
  const report = toReport(error, handled);
  const key = `${report.name ?? ''}|${report.message}|${report.stack?.slice(0, 300) ?? ''}`;
  if (seen.has(key)) {
    return;
  }
  seen.add(key);
  sent += 1;
  queue.push(report);
  if (queue.length >= MAX_BATCH) {
    flushErrors();
  } else if (timer === null) {
    timer = setTimeout(flushErrors, FLUSH_DELAY_MS);
  }
}

/** Listens for the errors nothing caught, and sends what is queued when the page is hidden. */
export function installErrorReporting(): void {
  if (installed) {
    return;
  }
  installed = true;
  window.addEventListener('error', (event: ErrorEvent) => {
    // A failed image or script load has no error object and says nothing useful.
    if ((event.error === undefined || event.error === null) && !event.message) {
      return;
    }
    reportError(event.error ?? event.message, { handled: false });
  });
  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    reportError(event.reason, { handled: false });
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flushErrors();
    }
  });
}

/** For tests: forget the queue, the counts and the listeners' guard. */
export function resetErrorReporting(): void {
  if (timer !== null) {
    clearTimeout(timer);
  }
  queue = [];
  sent = 0;
  seen.clear();
  timer = null;
  installed = false;
}
