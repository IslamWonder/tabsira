import type { SseMessage } from './sse';

/*
 * What the scan stream says (apps/api/src/scans/progress.py): `queued`,
 * `stage` for each of the four honest stages, `sound` once the scene is
 * matched to the ontology, then `done` or `failed`. Anything else, or a payload
 * of another shape, is ignored rather than guessed at.
 */

export const API_STAGES = ['understanding', 'searching', 'verifying', 'composing'] as const;
export type ApiStage = (typeof API_STAGES)[number];
export type StageEventState = 'started' | 'done' | 'failed';

export type ScanEvent =
  | { kind: 'queued'; run: number }
  | { kind: 'stage'; run: number; stage: ApiStage; state: StageEventState }
  | { kind: 'sound'; run: number; url: string }
  | { kind: 'done'; run: number }
  | { kind: 'failed'; run: number; code: string };

const STATES: readonly string[] = ['started', 'done', 'failed'];
/** Only the API's own sound route: the stream never sends the player elsewhere. */
const SOUND_URL = /^\/sounds\/ontology\/E[0-9]{3,4}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseData(data: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(data);
    return isRecord(value) ? value : null;
  } catch {
    return null;
  }
}

/** Reads one stream message as a typed event, or null when it is none we know. */
export function parseScanEvent(message: SseMessage): ScanEvent | null {
  const data = parseData(message.data);
  if (data === null || typeof data.run !== 'number') {
    return null;
  }
  const run = data.run;
  switch (message.event) {
    case 'queued':
      return { kind: 'queued', run };
    case 'sound':
      return typeof data.url === 'string' && SOUND_URL.test(data.url)
        ? { kind: 'sound', run, url: data.url }
        : null;
    case 'done':
      return { kind: 'done', run };
    case 'failed':
      return { kind: 'failed', run, code: typeof data.code === 'string' ? data.code : '' };
    case 'stage': {
      const stage = API_STAGES.find((candidate) => candidate === data.stage);
      const state = STATES.find((candidate) => candidate === data.state);
      return stage === undefined || state === undefined
        ? null
        : { kind: 'stage', run, stage, state: state as StageEventState };
    }
    default:
      return null;
  }
}

export function isTerminal(event: ScanEvent): boolean {
  return event.kind === 'done' || event.kind === 'failed';
}
