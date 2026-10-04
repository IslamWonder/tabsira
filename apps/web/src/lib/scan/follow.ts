import { readMessages, type SseMessage } from './sse';

export type FollowEnd = 'terminal' | 'aborted' | 'gave-up';

export interface FollowOptions {
  /** Opens the stream; `lastEventId` is what to resume after, null for the start. */
  open: (lastEventId: string | null, signal: AbortSignal) => Promise<Response>;
  /** Called for each message; returns true when it ended the run (`done` or `failed`). */
  handle: (message: SseMessage) => boolean;
  signal: AbortSignal;
  /** Where to resume, when an earlier stream of the same scan was already read. */
  after?: string | null;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
  maxFailures?: number;
}

export interface Followed {
  end: FollowEnd;
  /** The last event number read, to resume after it on a later stream. */
  lastEventId: string | null;
}

/** The pause before reconnecting: a second at least, so a stream that ends cleanly never spins. */
export function reconnectDelay(failures: number): number {
  return Math.min(1000 * 2 ** failures, 15_000);
}

export function waitFor(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', finish);
      resolve();
    };
    const timer = setTimeout(finish, milliseconds);
    signal.addEventListener('abort', finish);
  });
}

class Refused extends Error {}

/** A 4xx other than «too early» and «too many» will not change by asking again. */
function refuses(response: Response): boolean {
  const { status } = response;
  return status >= 400 && status < 500 && status !== 408 && status !== 429;
}

/**
 * Follows a scan's stream until its run ends, reconnecting after a drop with
 * `Last-Event-ID` so no event is missed or shown twice. A stream the server
 * closes without an end is opened again; repeated failures give up, and the
 * caller falls back to asking for the scan.
 */
export async function followEvents({
  open,
  handle,
  signal,
  after = null,
  wait = waitFor,
  maxFailures = 5,
}: FollowOptions): Promise<Followed> {
  let last = after;
  let failures = 0;
  while (!signal.aborted) {
    try {
      const response = await open(last, signal);
      if (refuses(response)) {
        throw new Refused();
      }
      if (!response.ok || response.body === null) {
        throw new Error('The stream did not open.');
      }
      for await (const message of readMessages(response.body)) {
        failures = 0;
        last = message.id ?? last;
        if (handle(message)) {
          return { end: 'terminal', lastEventId: last };
        }
      }
    } catch (error) {
      if (signal.aborted) {
        break;
      }
      if (error instanceof Refused) {
        return { end: 'gave-up', lastEventId: last };
      }
      failures += 1;
    }
    if (failures >= maxFailures) {
      return { end: 'gave-up', lastEventId: last };
    }
    await wait(reconnectDelay(failures), signal);
  }
  return { end: 'aborted', lastEventId: last };
}
