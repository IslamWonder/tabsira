'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useSession } from '@/account/session';
import { StatusScreen } from '@/components/app/status-screen';
import { PageContainer } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { GuideScene } from '@/components/ui/guide-scene';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';
import { getPost, viewPost } from '@/social/api';
import type { Post } from '@/social/types';
import { Comments } from './comments';
import { PostCard } from './post-card';

const C = messages.community;

type Load =
  | { kind: 'loading' }
  | { kind: 'ready'; post: Post }
  | { kind: 'gone' }
  | { kind: 'missing' }
  | { kind: 'withdrawn' }
  | { kind: 'failed'; failure: Failure };

function BackLink() {
  return (
    <Link
      href="/community"
      className="inline-flex min-h-10 items-center text-link underline-offset-4 hover:underline"
    >
      {C.back}
    </Link>
  );
}

/**
 * One post on its own page: the card with its evidence shown, then the
 * comments. 404 and 410 are told apart (a post that is gone says so; one the
 * viewer may not see is simply not found, so an id reveals nothing). The post
 * is asked for again when the session changes, since what the viewer may see
 * depends on who they are.
 */
export function PostScreen({
  postId,
  comments = false,
}: Readonly<{
  postId: string;
  /** The social_comments feature, read by the server: without it the thread is not shown. */
  comments?: boolean;
}>) {
  const session = useSession();
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const sessionStatus = session.status;
  // Counts the retries: each one asks the API again.
  const [attempt, setAttempt] = useState(0);
  // The post this page already told the API it opened: one view per opening, however often the
  // post is asked for again.
  const viewed = useRef<string | null>(null);
  const opened = load.kind === 'ready' && load.post.status === 'published';

  // Sent from the browser once the post is on screen, so the web server's render, a link
  // preview or a crawler is never a view. The API decides whether it counts.
  useEffect(() => {
    if (!opened || viewed.current === postId) {
      return;
    }
    viewed.current = postId;
    void viewPost(postId);
  }, [opened, postId]);

  // Asked again when the session changes (what the viewer may see depends on who they are)
  // and on every retry.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` counts the retries; each one asks again.
  useEffect(() => {
    if (sessionStatus === 'unknown') {
      return;
    }
    let current = true;
    setLoad({ kind: 'loading' });
    void getPost(postId).then((result) => {
      if (!current) {
        return;
      }
      if (result.ok) {
        setLoad({ kind: 'ready', post: result.data });
      } else if (result.status === 410) {
        setLoad({ kind: 'gone' });
      } else if (result.status === 404) {
        setLoad({ kind: 'missing' });
      } else {
        setLoad({ kind: 'failed', failure: result });
      }
    });
    return () => {
      current = false;
    };
  }, [postId, sessionStatus, attempt]);

  return (
    <PageContainer className="flex max-w-[48rem] flex-col gap-8 pt-[max(28px,env(safe-area-inset-top))] pb-6 tablet:pb-10">
      <BackLink />
      {load.kind === 'loading' ? (
        <p role="status" className="m-0 py-8 text-center text-fg-muted">
          {C.loading}
        </p>
      ) : null}
      {load.kind === 'ready' ? (
        <>
          <PostCard
            post={load.post}
            variant="full"
            headingLevel={1}
            comments={comments}
            onChange={(post) => setLoad({ kind: 'ready', post })}
            onRemoved={(reason) =>
              setLoad({ kind: reason === 'withdrawn' ? 'withdrawn' : 'missing' })
            }
          />
          {comments && load.post.status === 'published' ? (
            <Comments
              postId={load.post.id}
              authorHandle={load.post.author.handle}
              onAuthorBlocked={() => setLoad({ kind: 'missing' })}
            />
          ) : null}
        </>
      ) : null}
      {load.kind === 'withdrawn' ? (
        <div role="status" className="flex flex-col items-start gap-4">
          <Notice tone="success">{C.publish.withdrawn}</Notice>
          <LinkButton href="/community" variant="secondary">
            {C.back}
          </LinkButton>
        </div>
      ) : null}
      {load.kind === 'gone' || load.kind === 'missing' ? (
        <StatusScreen
          scene="lantern"
          title={load.kind === 'gone' ? C.gone.title : C.notFound.title}
          description={load.kind === 'gone' ? C.gone.description : C.notFound.description}
          className="py-10"
        >
          <LinkButton href="/community" variant="secondary">
            {C.back}
          </LinkButton>
        </StatusScreen>
      ) : null}
      {load.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-center gap-3 py-6 text-center">
          <GuideScene scene="lantern" size={112} />
          <Notice tone="error">{failureMessage(load.failure)}</Notice>
          <Button variant="ghost" onClick={() => setAttempt((count) => count + 1)}>
            {C.retry}
          </Button>
        </div>
      ) : null}
    </PageContainer>
  );
}
