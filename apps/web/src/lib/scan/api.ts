import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';
import { apiOrigin } from '@/lib/site';

/*
 * The calls of the journey from a photo to an insight, typed from the API's own
 * OpenAPI document. Every one answers a Result: the data, or one stable error
 * code. Ids are strings (a public id is beyond 2^53) and stay strings.
 */

type Schemas = components['schemas'];
export type Scan = Schemas['ScanOut'];
export type ScanEntity = Schemas['ScanEntityOut'];
export type InsightSummary = Schemas['InsightSummary'];
export type Tutorial = Schemas['TutorialOut'];
export type Insight = Schemas['InsightOut'];
export type ChatReply = Schemas['ChatReply'];
export type ChatMessage = Schemas['ChatMessageOut'];
export type Completion = Schemas['CompletionOut'];
export type ActionChoice = Schemas['ActionIn']['choice'];
export type ActionResult = Schemas['ActionOut'];
export type Progress = Schemas['ProgressOut'];

/** Starts a scan from a photo; the API strips its metadata before it keeps it. */
export function startScanFromFile(file: File, signal?: AbortSignal): Promise<Result<Scan>> {
  const form = new FormData();
  form.append('image', file);
  return attempt(api.POST('/scans', { body: { image: '' }, bodySerializer: () => form, signal }));
}

/** Starts a scan from a photo's public address; the API fetches it under its own limits. */
export function startScanFromLink(url: string, signal?: AbortSignal): Promise<Result<Scan>> {
  return attempt(api.POST('/scans', { body: { url }, signal }));
}

export function getScan(id: string, signal?: AbortSignal): Promise<Result<Scan>> {
  return attempt(api.GET('/scans/{scan_id}', { params: { path: { scan_id: id } }, signal }));
}

export function focusScan(id: string, entityId: string): Promise<Result<Scan>> {
  return attempt(
    api.POST('/scans/{scan_id}/focus', {
      params: { path: { scan_id: id } },
      body: { entity_id: entityId },
    })
  );
}

export function clarifyScan(id: string, answer: string): Promise<Result<Scan>> {
  return attempt(
    api.POST('/scans/{scan_id}/clarify', {
      params: { path: { scan_id: id } },
      body: { answer },
    })
  );
}

export function getRainTutorial(signal?: AbortSignal): Promise<Result<Tutorial>> {
  return attempt(api.GET('/tutorial/rain', { signal }));
}

/** Keeps the caller's copy of a tutorial insight (made once), so it can be completed and discussed. */
export function keepRainInsight(slug: string): Promise<Result<Insight>> {
  return attempt(api.POST('/tutorial/rain/insights/{slug}', { params: { path: { slug } } }));
}

export function getInsight(id: string, signal?: AbortSignal): Promise<Result<Insight>> {
  return attempt(
    api.GET('/insights/{insight_id}', { params: { path: { insight_id: id } }, signal })
  );
}

/** One question to the insight's chat; the same key is answered and counted once. */
export function askInsight(id: string, message: string, key: string): Promise<Result<ChatReply>> {
  return attempt(
    api.POST('/insights/{insight_id}/chat', {
      params: { path: { insight_id: id } },
      body: { message, idempotencyKey: key },
    })
  );
}

export function declareAction(id: string, choice: ActionChoice): Promise<Result<ActionResult>> {
  return attempt(
    api.POST('/insights/{insight_id}/action', {
      params: { path: { insight_id: id } },
      body: { choice },
    })
  );
}

/** the done action: saved once, however many times it is sent. */
export function completeInsight(id: string): Promise<Result<Completion>> {
  return attempt(
    api.POST('/insights/{insight_id}/complete', { params: { path: { insight_id: id } } })
  );
}

/** The learner's practice; `timeZone` (an IANA name) decides what «today» means for the daily quest. */
export function getProgress(timeZone: string): Promise<Result<Progress>> {
  return attempt(api.GET('/me/progress', { params: { query: { tz: timeZone } } }));
}

/** The address of a path the API serves (the photo of a scan, the stream of its events). */
export function apiUrl(path: string): string {
  return `${apiOrigin()}${path}`;
}

/** Opens a scan's event stream, resuming after `lastEventId` when there is one. */
export function openScanStream(
  path: string,
  lastEventId: string | null,
  signal: AbortSignal
): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  if (lastEventId !== null) {
    headers['Last-Event-ID'] = lastEventId;
  }
  return globalThis.fetch(apiUrl(path), {
    headers,
    credentials: 'include',
    cache: 'no-store',
    signal,
  });
}
