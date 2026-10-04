import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type Progress = components['schemas']['ProgressOut'];
export type Badge = components['schemas']['BadgeOut'];
export type Star = components['schemas']['StarOut'];

/** What the learner's recorded practice adds up to; «today» follows the device's time zone. */
export function loadProgress(timeZone: string): Promise<Result<Progress>> {
  return attempt(api.GET('/me/progress', { params: { query: { tz: timeZone } } }));
}
