'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useId, useState } from 'react';
import { useSession } from '@/account/session';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { TextArea } from '@/components/ui/text-area';
import { failureMessage } from '@/lib/api/failure-message';
import { formatWhen } from '@/lib/dates';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { commentsPage, createComment, deleteComment } from '@/social/api';
import { memberLabel, profilePath } from '@/social/identity';
import { COMMENT_MAX, type Comment } from '@/social/types';
import { usePages } from '@/social/use-pages';
import { AccessNote, BlockSheet, ReportSheet } from './sheets';

const K = messages.community.comments;
const C = messages.community;

interface CommentFormProps {
  postId: string;
  /** Answering a comment: the reply goes under it. */
  parent?: Comment;
  onCreated: (comment: Comment) => void;
  onCancel?: () => void;
}

/** Write a comment or a reply; the guard judges it before anyone else sees it. */
function CommentForm({ postId, parent, onCreated, onCancel }: Readonly<CommentFormProps>) {
  const access = useAccess();
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const canWrite = access === 'member';
  const length = Array.from(body.trim()).length;

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (length === 0 || length > COMMENT_MAX) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await createComment(postId, body.trim(), parent?.id ?? null);
    setBusy(false);
    if (result.ok) {
      setBody('');
      onCreated(result.data);
    } else {
      setFailure(failureMessage(result));
    }
  };

  return (
    <form onSubmit={send} className="flex flex-col gap-3">
      <TextArea
        label={parent === undefined ? K.write : K.writeReply(memberLabel(parent.author))}
        hint={K.limit(COMMENT_MAX)}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        maxChars={COMMENT_MAX}
        rows={3}
        disabled={!canWrite}
      />
      <AccessNote access={access} guest={K.signIn} unverified={K.verify} identity={K.identity} />
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit" disabled={!canWrite || busy || length === 0 || length > COMMENT_MAX}>
          {busy ? K.sending : K.send}
        </Button>
        {onCancel === undefined ? null : (
          <Button variant="ghost" onClick={onCancel}>
            {K.cancelReply}
          </Button>
        )}
      </div>
    </form>
  );
}

interface CommentItemProps {
  postId: string;
  comment: Comment;
  /** A reply cannot be replied to: the thread is one level deep. */
  canReply: boolean;
  onReply?: () => void;
  onDeleted: () => void;
  onAuthorBlocked: (handle: string) => void;
}

function CommentItem({
  postId,
  comment,
  canReply,
  onReply,
  onDeleted,
  onAuthorBlocked,
}: Readonly<CommentItemProps>) {
  const access = useAccess();
  const [open, setOpen] = useState<'none' | 'report' | 'block'>('none');
  const [deleting, setDeleting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const remove = async () => {
    setDeleting(true);
    setFailure(null);
    const result = await deleteComment(postId, comment.id);
    setDeleting(false);
    if (result.ok) {
      onDeleted();
    } else {
      setFailure(failureMessage(result));
    }
  };
  return (
    <div className="flex flex-col gap-2" data-comment-id={comment.id}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.875rem]">
        <Link
          href={profilePath(comment.author.handle)}
          className="font-semibold text-fg underline-offset-4 hover:underline"
        >
          {memberLabel(comment.author)}
        </Link>
        <time dateTime={comment.created_at} className="text-fg-muted">
          {formatWhen(comment.created_at)}
        </time>
        {comment.is_mine ? <Chip>{K.mine}</Chip> : null}
        {comment.is_mine && comment.status !== 'published' ? (
          <Chip tone="primary">{C.post.status[comment.status]}</Chip>
        ) : null}
      </div>
      <p className="m-0 whitespace-pre-wrap text-fg leading-[1.85]">{comment.body}</p>
      {comment.is_mine && comment.status_message !== null ? (
        <p className="m-0 text-[0.875rem] text-fg-soft">{comment.status_message}</p>
      ) : null}
      <div className="flex flex-wrap items-center gap-1 text-[0.875rem]">
        {canReply && access !== 'guest' ? (
          <Button variant="ghost" onClick={onReply} className="min-h-10 px-3 text-[0.875rem]">
            {K.reply}
          </Button>
        ) : null}
        {comment.is_mine ? (
          <Button
            variant="ghost"
            onClick={remove}
            disabled={deleting}
            className="min-h-10 px-3 text-[0.875rem]"
          >
            {deleting ? K.deleting : K.delete}
          </Button>
        ) : (
          <>
            <Button
              variant="ghost"
              onClick={() => setOpen('report')}
              className="min-h-10 px-3 text-[0.875rem]"
            >
              {C.report.action}
            </Button>
            {access === 'guest' || access === 'unknown' ? null : (
              <Button
                variant="ghost"
                onClick={() => setOpen('block')}
                className="min-h-10 px-3 text-[0.875rem]"
              >
                {C.block.action}
              </Button>
            )}
          </>
        )}
      </div>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
      <ReportSheet
        open={open === 'report'}
        onClose={() => setOpen('none')}
        targetType="comment"
        targetId={comment.id}
      />
      <BlockSheet
        open={open === 'block'}
        onClose={() => setOpen('none')}
        handle={comment.author.handle}
        publicName={memberLabel(comment.author)}
        onBlocked={() => onAuthorBlocked(comment.author.handle)}
      />
    </div>
  );
}

/**
 * A post's comments, oldest first, each with its replies one level deep
 * (docs/SOCIAL_NETWORK.md «Comments»). The viewer's own comment appears at
 * once with the state the guard gave it; nobody else sees it until it is
 * published. A comment by someone the viewer blocks leaves the thread.
 */
export function Comments({
  postId,
  authorHandle,
  onAuthorBlocked,
}: Readonly<{
  postId: string;
  /** The post's author: blocking them from a comment hides the post too. */
  authorHandle?: string;
  onAuthorBlocked?: () => void;
}>) {
  const headingId = useId();
  const fetchPage = useCallback((cursor: string | null) => commentsPage(postId, cursor), [postId]);
  const session = useSession();
  const pages = usePages<Comment>(
    fetchPage,
    `comments:${postId}:${session.status}`,
    session.status !== 'unknown'
  );
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [deleted, setDeleted] = useState(false);

  const removeAuthor = (handle: string) => {
    pages.replace((thread) => thread.author.handle === handle, null);
    if (handle === authorHandle) {
      onAuthorBlocked?.();
    }
  };
  const withoutAuthorReplies = (handle: string) => {
    for (const thread of pages.items) {
      if (thread.replies.some((reply) => reply.author.handle === handle)) {
        pages.replace(
          (item) => item.id === thread.id,
          // From the thread the list holds now: an earlier deletion in the same
          // thread must not be undone by this one.
          (current) => ({
            ...current,
            replies: current.replies.filter((reply) => reply.author.handle !== handle),
          })
        );
      }
    }
  };

  return (
    <section id="comments" aria-labelledby={headingId} className="flex scroll-mt-28 flex-col gap-6">
      <h2 id={headingId} className="m-0 font-semibold text-subheading text-fg">
        {K.title}
      </h2>
      <CommentForm postId={postId} onCreated={pages.append} />
      {deleted ? (
        <p role="status" className="m-0 text-fg-soft text-sm">
          {K.deleted}
        </p>
      ) : null}
      {pages.items.length === 0 && pages.status.kind === 'loading' ? (
        <p role="status" className="m-0 text-fg-muted">
          {K.loading}
        </p>
      ) : null}
      {pages.items.length === 0 && pages.status.kind === 'ready' ? (
        <p role="status" className="m-0 text-fg-soft">
          {K.empty}
        </p>
      ) : null}
      <ol className="m-0 flex list-none flex-col gap-6 p-0">
        {pages.items.map((thread) => (
          <li key={thread.id} className="flex flex-col gap-4">
            <CommentItem
              postId={postId}
              comment={thread}
              canReply
              onReply={() => setReplyTo(thread)}
              onDeleted={() => {
                pages.replace((item) => item.id === thread.id, null);
                setDeleted(true);
              }}
              onAuthorBlocked={(handle) => {
                removeAuthor(handle);
                withoutAuthorReplies(handle);
              }}
            />
            {thread.replies.length === 0 && replyTo?.id !== thread.id ? null : (
              <ol className="m-0 flex list-none flex-col gap-4 border-line border-s-2 p-0 ps-4">
                {thread.replies.map((reply) => (
                  <li key={reply.id}>
                    <CommentItem
                      postId={postId}
                      comment={reply}
                      canReply={false}
                      onDeleted={() => {
                        pages.replace(
                          (item) => item.id === thread.id,
                          // From the thread the list holds now: a reply deleted
                          // while another answer was in flight stays gone.
                          (current) => ({
                            ...current,
                            replies: current.replies.filter((item) => item.id !== reply.id),
                          })
                        );
                        setDeleted(true);
                      }}
                      onAuthorBlocked={(handle) => {
                        removeAuthor(handle);
                        withoutAuthorReplies(handle);
                      }}
                    />
                  </li>
                ))}
                {replyTo?.id === thread.id ? (
                  <li>
                    <CommentForm
                      postId={postId}
                      parent={thread}
                      onCancel={() => setReplyTo(null)}
                      onCreated={(reply) => {
                        pages.replace(
                          (item) => item.id === thread.id,
                          // From the thread the list holds now: a reply deleted
                          // while this one was being sent is not brought back.
                          (current) => ({ ...current, replies: [...current.replies, reply] })
                        );
                        setReplyTo(null);
                      }}
                    />
                  </li>
                ) : null}
              </ol>
            )}
          </li>
        ))}
      </ol>
      {pages.status.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{pages.status.message}</Notice>
          <Button
            variant="ghost"
            onClick={pages.items.length === 0 ? pages.reload : pages.loadMore}
          >
            {C.retry}
          </Button>
        </div>
      ) : null}
      {pages.status.kind === 'loading-more' ? (
        <p role="status" className="m-0 text-fg-muted">
          {C.loadingMore}
        </p>
      ) : null}
      {pages.status.kind === 'ready' && pages.status.more ? (
        <Button variant="secondary" onClick={pages.loadMore} className="self-start">
          {K.loadMore}
        </Button>
      ) : null}
    </section>
  );
}
