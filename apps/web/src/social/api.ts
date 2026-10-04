import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type {
  Comment,
  CommentPage,
  FeedPage,
  MemberProfile,
  MyPostsPage,
  Post,
  PostVisibility,
  PublicIdentity,
  Reaction,
  ReportReason,
  ReportTarget,
} from './types';

/*
 * Every call of the social network, one function each, typed by the generated
 * client. Nothing here decides who may do what: the API checks the session,
 * the owner, the state, the audience and the blocks on every route, and the
 * screens only show the answer.
 */

export type FeedKind = 'for-you' | 'following' | 'latest';

const FEED_PATH = {
  'for-you': '/feed/for-you',
  following: '/feed/following',
  latest: '/feed/latest',
} as const;

function paged(cursor: string | null) {
  return cursor === null ? {} : { cursor };
}

export function feedPage(kind: FeedKind, cursor: string | null): Promise<Result<FeedPage>> {
  return attempt(api.GET(FEED_PATH[kind], { params: { query: paged(cursor) } }));
}

export function memberPosts(handle: string, cursor: string | null): Promise<Result<FeedPage>> {
  return attempt(
    api.GET('/u/{handle}/posts', { params: { path: { handle }, query: paged(cursor) } })
  );
}

export function bookmarksPage(cursor: string | null): Promise<Result<FeedPage>> {
  return attempt(api.GET('/me/bookmarks', { params: { query: paged(cursor) } }));
}

export function myPostsPage(cursor: string | null): Promise<Result<MyPostsPage>> {
  return attempt(api.GET('/me/posts', { params: { query: paged(cursor) } }));
}

export function getPost(postId: string): Promise<Result<Post>> {
  return attempt(api.GET('/posts/{post_id}', { params: { path: { post_id: postId } } }));
}

export interface DraftInput {
  insightId: string;
  reflection: string | null;
  visibility: PostVisibility;
}

export function createDraft({
  insightId,
  reflection,
  visibility,
}: DraftInput): Promise<Result<Post>> {
  // The photo choice has no control yet: a post made from here never shows the photo.
  return attempt(
    api.POST('/posts', { body: { insight_id: insightId, reflection, visibility, photo: false } })
  );
}

export function editDraft(
  postId: string,
  changes: { reflection?: string | null; visibility?: PostVisibility }
): Promise<Result<Post>> {
  return attempt(
    api.PATCH('/posts/{post_id}', { params: { path: { post_id: postId } }, body: changes })
  );
}

export function submitPost(postId: string): Promise<Result<Post>> {
  return attempt(api.POST('/posts/{post_id}/submit', { params: { path: { post_id: postId } } }));
}

export function withdrawPost(postId: string): Promise<Result<unknown>> {
  return attempt(api.DELETE('/posts/{post_id}', { params: { path: { post_id: postId } } }));
}

export function setLike(postId: string, liked: boolean): Promise<Result<Reaction>> {
  const params = { params: { path: { post_id: postId } } };
  return attempt(
    liked ? api.PUT('/posts/{post_id}/like', params) : api.DELETE('/posts/{post_id}/like', params)
  );
}

export function setBookmark(postId: string, saved: boolean): Promise<Result<unknown>> {
  const params = { params: { path: { post_id: postId } } };
  return attempt(
    saved
      ? api.PUT('/posts/{post_id}/bookmark', params)
      : api.DELETE('/posts/{post_id}/bookmark', params)
  );
}

export function commentsPage(postId: string, cursor: string | null): Promise<Result<CommentPage>> {
  return attempt(
    api.GET('/posts/{post_id}/comments', {
      params: { path: { post_id: postId }, query: paged(cursor) },
    })
  );
}

export function createComment(
  postId: string,
  body: string,
  parentId: string | null
): Promise<Result<Comment>> {
  return attempt(
    api.POST('/posts/{post_id}/comments', {
      params: { path: { post_id: postId } },
      body: { body, parent_id: parentId },
    })
  );
}

export function deleteComment(postId: string, commentId: string): Promise<Result<unknown>> {
  return attempt(
    api.DELETE('/posts/{post_id}/comments/{comment_id}', {
      params: { path: { post_id: postId, comment_id: commentId } },
    })
  );
}

export function fileReport(input: {
  targetType: ReportTarget;
  targetId: string;
  reason: ReportReason;
  details: string | null;
}): Promise<Result<{ id: string }>> {
  return attempt(
    api.POST('/reports', {
      body: {
        target_type: input.targetType,
        target_id: input.targetId,
        reason: input.reason,
        details: input.details,
      },
    })
  );
}

export function getProfile(handle: string): Promise<Result<MemberProfile>> {
  return attempt(api.GET('/u/{handle}', { params: { path: { handle } } }));
}

export function setFollow(handle: string, follow: boolean): Promise<Result<unknown>> {
  const params = { params: { path: { handle } } };
  return attempt(
    follow ? api.PUT('/u/{handle}/follow', params) : api.DELETE('/u/{handle}/follow', params)
  );
}

export function setBlock(handle: string, blocked: boolean): Promise<Result<unknown>> {
  const params = { params: { path: { handle } } };
  return attempt(
    blocked ? api.PUT('/blocks/{handle}', params) : api.DELETE('/blocks/{handle}', params)
  );
}

export function listBlocks(): Promise<Result<{ handle: string; public_name: string }[]>> {
  return attempt(api.GET('/blocks'));
}

export function getIdentity(): Promise<Result<PublicIdentity>> {
  return attempt(api.GET('/me/public-identity'));
}

export function putIdentity(handle: string, publicName: string): Promise<Result<PublicIdentity>> {
  return attempt(api.PUT('/me/public-identity', { body: { handle, public_name: publicName } }));
}
