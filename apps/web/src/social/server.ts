import { SERVER_API_TIMEOUT_MS, serverApiOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { MemberProfile, Post } from './types';

/*
 * What the web server reads to write a public page's metadata (docs/SEO.md):
 * the post or the profile as a stranger sees it, with no cookie, so the
 * description never carries anything the viewer alone may read. A short
 * timeout: a slow API never holds the page (AGENTS.md lessons).
 */

function client() {
  return createApiClient({ baseUrl: serverApiOrigin() });
}

const timeout = () => AbortSignal.timeout(SERVER_API_TIMEOUT_MS);

export function postOnServer(postId: string): Promise<Result<Post>> {
  return attempt(
    client().GET('/posts/{post_id}', { params: { path: { post_id: postId } }, signal: timeout() })
  );
}

export function profileOnServer(handle: string): Promise<Result<MemberProfile>> {
  return attempt(client().GET('/u/{handle}', { params: { path: { handle } }, signal: timeout() }));
}
