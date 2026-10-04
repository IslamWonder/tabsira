import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type Publication = components['schemas']['PublicationOut'];

/** Makes the caller's own insight public; asking again changes nothing and answers its path. */
export function publishInsight(id: string): Promise<Result<Publication>> {
  return attempt(
    api.PUT('/insights/{insight_id}/publication', { params: { path: { insight_id: id } } })
  );
}

/** Takes the insight down at once; its public address answers 404 from then on. */
export function withdrawInsight(id: string): Promise<Result<Publication>> {
  return attempt(
    api.DELETE('/insights/{insight_id}/publication', { params: { path: { insight_id: id } } })
  );
}
