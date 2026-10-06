import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type Publication = components['schemas']['PublicationOut'];
export type InsightPost = components['schemas']['PostOut'];

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

/**
 * Publishes the insight in the network (decision 68): its one post, public and without a
 * reflection, made if it has none; asking again answers the same post. `photo` is the owner's
 * choice to show the kept photo with a new post.
 */
export function publishPost(id: string, photo = false): Promise<Result<InsightPost>> {
  return attempt(
    api.PUT('/insights/{insight_id}/post', {
      params: { path: { insight_id: id } },
      body: { photo },
    })
  );
}
