'use client';

import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { messages } from '@/messages';
import type { Post } from '@/social/types';
import type { Pages } from '@/social/use-pages';
import { PostCard } from './post-card';

const C = messages.community;

export interface FeedListProps {
  pages: Pages<Post>;
  /** What to say when the first page is empty; the API's `empty_reason` picks one. */
  emptyText: (reason: string | null) => string;
  /** Shown instead of the list, for a feed the viewer must sign in for. */
  gate?: ReactNode;
  headingLevel?: 2 | 3;
  /** The social_comments feature, passed down from the server page. */
  comments?: boolean;
  /** The viewer blocked a member from one of the cards; the page may have more of them to hide. */
  onAuthorBlocked?: (handle: string) => void;
}

/**
 * A feed, one post after another in a single column (never a grid: tajriba
 * §5), with the honest states of tajriba §8: loading, empty with its reason,
 * failed with a retry, and a button for the next page. No post is ever
 * invented to fill it.
 */
export function FeedList({
  pages,
  emptyText,
  gate,
  headingLevel = 2,
  comments = false,
  onAuthorBlocked,
}: FeedListProps) {
  if (gate !== undefined) {
    return <div className="py-6">{gate}</div>;
  }
  const { items, status } = pages;
  return (
    <div className="flex flex-col gap-5">
      {items.length === 0 && status.kind === 'loading' ? (
        <p role="status" className="m-0 py-8 text-center text-fg-muted">
          {C.loading}
        </p>
      ) : null}
      {items.length === 0 && status.kind === 'ready' ? (
        <p role="status" className="m-0 py-8 text-center text-fg-soft leading-[1.85]">
          {emptyText(status.emptyReason)}
        </p>
      ) : null}
      {items.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          headingLevel={headingLevel}
          comments={comments}
          onChange={(next) => pages.replace((item) => item.id === post.id, next)}
          onRemoved={(reason) => {
            pages.replace(
              (item) =>
                reason === 'blocked'
                  ? item.author.handle === post.author.handle
                  : item.id === post.id,
              null
            );
            if (reason === 'blocked') {
              onAuthorBlocked?.(post.author.handle);
            }
          }}
        />
      ))}
      {status.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{status.message}</Notice>
          <Button variant="ghost" onClick={items.length === 0 ? pages.reload : pages.loadMore}>
            {C.retry}
          </Button>
        </div>
      ) : null}
      {status.kind === 'loading-more' ? (
        <p role="status" className="m-0 py-2 text-center text-fg-muted">
          {C.loadingMore}
        </p>
      ) : null}
      {status.kind === 'ready' && status.more ? (
        <Button variant="secondary" onClick={pages.loadMore} className="self-center">
          {C.loadMore}
        </Button>
      ) : null}
      {status.kind === 'ready' && !status.more && items.length > 0 ? (
        <p className="m-0 py-2 text-center text-[0.875rem] text-fg-muted">{C.end}</p>
      ) : null}
    </div>
  );
}
