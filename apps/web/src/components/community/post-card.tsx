'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useId, useState } from 'react';
import { signInHref } from '@/account/links';
import {
  BookmarkIcon,
  CommentIcon,
  EyeIcon,
  MoreIcon,
  SparkIcon,
  ThanksIcon,
} from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { failureMessage } from '@/lib/api/failure-message';
import { cx } from '@/lib/cx';
import { formatWhen } from '@/lib/dates';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { setBookmark, setReaction } from '@/social/api';
import { memberLabel, postPath, profilePath } from '@/social/identity';
import type { Post, ReactionKind } from '@/social/types';
import { PostEvidence } from './evidence';
import { FollowToggle } from './follow-toggle';
import { PublicPhoto } from './public-photo';
import { BlockSheet, ReportSheet, WithdrawSheet } from './sheets';
import { WhySheet } from './why-sheet';

const M = messages.community.post;
const C = messages.community;

export interface PostCardProps {
  post: Post;
  /** The post after a reaction or a save, so the list shows what the API kept. */
  onChange: (post: Post) => void;
  /** The post left the viewer's lists: withdrawn, or its author blocked. */
  onRemoved?: (reason: 'withdrawn' | 'blocked') => void;
  /** In a feed the evidence waits behind a reveal; on its own page it is shown at once. */
  variant?: 'feed' | 'full';
  headingLevel?: 1 | 2 | 3;
  /** The social_comments feature, read by the server: without it no comment link or count is shown. */
  comments?: boolean;
  className?: string;
}

/** The reveal names what the post holds: a verse and a hadith, one of them, or nothing shown. */
export function revealLabel(insight: Post['insight']): string {
  if (insight.quran.length > 0 && insight.hadith.length > 0) {
    return M.reveal;
  }
  if (insight.quran.length > 0) {
    return M.revealQuran;
  }
  return insight.hadith.length > 0 ? M.revealHadith : M.revealNone;
}

/** The author's moderation state, shown to the author alone (the API returns it to nobody else). */
export function StatusChip({ post }: Readonly<{ post: Post }>) {
  if (post.status === 'published') {
    return null;
  }
  return (
    <div className="flex flex-col gap-1.5" data-testid="post-status">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={post.status === 'draft' ? 'neutral' : 'primary'}>{M.status[post.status]}</Chip>
        <span className="text-[0.8125rem] text-fg-muted">{M.statusHint}</span>
      </div>
      {post.status_message === null ? null : (
        <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.75]">{post.status_message}</p>
      )}
    </div>
  );
}

/** The author's own words, apart from the insight and labelled as theirs, whatever they say. */
function ReflectionBlock({ post }: Readonly<{ post: Post }>) {
  if (post.reflection === null) {
    return null;
  }
  return (
    <section aria-label={M.reflection} className="flex flex-col gap-2 border-line border-s-2 ps-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip>{M.reflection}</Chip>
        <span className="text-[0.8125rem] text-fg-muted">{M.reflectionNote}</span>
      </div>
      <p
        className="m-0 whitespace-pre-wrap text-[1.0625rem] text-fg leading-[1.9]"
        data-source="user"
      >
        {post.reflection.text}
      </p>
      {post.reflection.looks_like_scripture ? (
        <p className="m-0 text-[0.8125rem] text-fg-muted">{M.looksLikeScripture}</p>
      ) : null}
    </section>
  );
}

/** The two reactions of decision 61, in the order they are shown. */
const REACTIONS = [
  { kind: 'benefited', Icon: SparkIcon },
  { kind: 'jazak', Icon: ThanksIcon },
] as const;

/**
 * One post as an illuminated card (DESIGN_DECISION.md «Game feel»): the
 * author, the insight's title and glimpse, the platform's explanation, the
 * verified pair (behind a reveal in a feed), the author's reflection labelled
 * as theirs, and the reactions
 * with their public counts, the comments, the views, a save and the «more» sheet. Hover changes
 * colour only.
 */
export function PostCard({
  post,
  onChange,
  onRemoved,
  variant = 'feed',
  headingLevel = 2,
  comments = false,
  className,
}: Readonly<PostCardProps>) {
  const titleId = useId();
  const pathname = usePathname();
  const access = useAccess();
  const [revealed, setRevealed] = useState(variant === 'full');
  const [open, setOpen] = useState<'none' | 'why' | 'more' | 'report' | 'block' | 'withdraw'>(
    'none'
  );
  const [note, setNote] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const Heading = `h${headingLevel}` as const;
  const isAuthor = post.viewer?.is_author === true;
  const [followsAuthor, setFollowsAuthor] = useState(post.viewer?.follows_author === true);
  const when = post.published_at ?? post.created_at;
  const closeSheets = () => setOpen('none');

  const given = post.viewer?.reactions ?? [];

  const react = async (kind: ReactionKind | 'bookmark') => {
    if (access === 'guest' || access === 'unverified') {
      setNote(access === 'guest' ? C.reactions.signIn : C.reactions.verify);
      return;
    }
    setNote(null);
    setFailure(null);
    if (kind !== 'bookmark') {
      const result = await setReaction(post.id, kind, !given.includes(kind));
      if (result.ok) {
        onChange({
          ...post,
          reactions: result.data.reactions,
          viewer: {
            reactions: result.data.mine,
            bookmarked: post.viewer?.bookmarked === true,
            is_author: isAuthor,
            follows_author: followsAuthor,
          },
        });
      } else {
        setFailure(failureMessage(result));
      }
      return;
    }
    const saved = post.viewer?.bookmarked !== true;
    const result = await setBookmark(post.id, saved);
    if (result.ok) {
      onChange({
        ...post,
        viewer: {
          reactions: given,
          bookmarked: saved,
          is_author: isAuthor,
          follows_author: followsAuthor,
        },
      });
    } else {
      setFailure(failureMessage(result));
    }
  };

  return (
    <GlassPanel
      as="article"
      ornate
      aria-labelledby={titleId}
      data-post-id={post.id}
      className={cx('flex flex-col gap-5 tablet:p-7', className)}
    >
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <Link
            href={profilePath(post.author.handle)}
            aria-label={M.authorLink(memberLabel(post.author))}
            className="flex min-h-10 flex-wrap items-center gap-x-2 text-fg underline-offset-4 hover:underline"
          >
            {post.author.public_name === null ? null : (
              <span className="font-semibold">{post.author.public_name}</span>
            )}
            <bdi className="text-[0.875rem] text-fg-muted">@{post.author.handle}</bdi>
            {post.author.country ? (
              <span className="text-[0.875rem] text-fg-muted">
                {M.authorCountry(post.author.country.name)}
              </span>
            ) : null}
          </Link>
          {post.viewer === null || isAuthor ? null : (
            <FollowToggle
              handle={post.author.handle}
              follows={followsAuthor}
              onChange={setFollowsAuthor}
              compact
            />
          )}
          <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-fg-muted">
            {post.visibility === 'followers' ? <Chip>{M.visibility.followers}</Chip> : null}
            <time dateTime={when}>{formatWhen(when)}</time>
          </div>
        </div>
        {isAuthor ? <StatusChip post={post} /> : null}
        <Heading id={titleId} className="m-0 font-bold font-display text-heading text-gilded">
          {variant === 'feed' ? (
            <Link href={postPath(post.id)} className="text-gilded no-underline hover:underline">
              {post.insight.title}
            </Link>
          ) : (
            post.insight.title
          )}
        </Heading>
        <p className="m-0 text-[1.0625rem] text-fg-soft leading-[1.85]">{post.insight.glimpse}</p>
      </header>

      {variant === 'full' ? (
        <PublicPhoto url={post.insight.photo_url} alt={M.photoAlt(post.insight.title)} />
      ) : null}

      <section aria-label={M.explanation} className="flex flex-col items-start gap-2">
        <Chip tone="primary">{M.explanation}</Chip>
        <p className="m-0 text-fg leading-[1.9]">{post.insight.explanation}</p>
      </section>

      {revealed ? (
        <PostEvidence insight={post.insight} headingLevel={headingLevel === 1 ? 2 : 3} />
      ) : (
        <Button
          variant="secondary"
          aria-expanded={false}
          onClick={() => setRevealed(true)}
          className="self-start"
        >
          {revealLabel(post.insight)}
        </Button>
      )}

      {post.insight.step === null ? null : (
        <p className="m-0 rounded-[var(--radius-card)] border border-[var(--step-border)] bg-[linear-gradient(135deg,var(--step-surface-from),var(--step-surface-to))] px-4 py-3 text-[0.9375rem] text-fg leading-[1.8]">
          <strong className="font-semibold text-step-title">{M.step}</strong> · {post.insight.step}
        </p>
      )}

      <ReflectionBlock post={post} />

      {post.why === null ? null : (
        <button
          type="button"
          aria-haspopup="dialog"
          onClick={() => setOpen('why')}
          className="flex min-h-10 items-center gap-2 self-start text-[0.875rem] text-fg-muted underline-offset-4 hover:text-fg hover:underline"
        >
          <span className="text-fg-soft">{post.why.text}</span>{' '}
          <span className="text-link">{M.why}</span>
        </button>
      )}

      <footer className="flex flex-col gap-2 border-line border-t pt-3">
        <div className="flex flex-wrap items-center gap-1">
          {REACTIONS.map(({ kind, Icon }) => {
            const pressed = given.includes(kind);
            return (
              <button
                key={kind}
                type="button"
                aria-pressed={pressed}
                onClick={() => void react(kind)}
                className={cx(
                  'inline-flex min-h-12 items-center gap-2 rounded-full px-3 text-[0.9375rem] transition-colors duration-200',
                  pressed
                    ? 'text-primary [text-shadow:var(--hadith-words-glow)]'
                    : 'text-fg-soft hover:text-fg'
                )}
              >
                <Icon
                  width="20"
                  height="20"
                  className={pressed ? 'drop-shadow-[0_0_8px_var(--glow-gold)]' : undefined}
                />
                {M[kind]}
                {post.reactions[kind] > 0 ? (
                  <>
                    {' '}
                    <span className="text-[0.8125rem] text-fg-muted tabular-nums">
                      {post.reactions[kind]}
                    </span>
                  </>
                ) : null}
              </button>
            );
          })}
          {comments ? (
            <Link
              href={`${postPath(post.id)}#comments`}
              className="inline-flex min-h-12 items-center gap-2 rounded-full px-3 text-[0.9375rem] text-fg-soft transition-colors duration-200 hover:text-fg"
            >
              <CommentIcon width="20" height="20" />
              {M.commentCount(post.comment_count)}
            </Link>
          ) : null}
          {post.status === 'published' ? (
            <span className="inline-flex min-h-12 items-center gap-2 px-3 text-[0.9375rem] text-fg-muted tabular-nums">
              <EyeIcon width="20" height="20" />
              {M.viewCount(post.views_count)}
            </span>
          ) : null}
          <button
            type="button"
            aria-pressed={post.viewer?.bookmarked === true}
            onClick={() => void react('bookmark')}
            className={cx(
              'inline-flex min-h-12 items-center gap-2 rounded-full px-3 text-[0.9375rem] transition-colors duration-200',
              post.viewer?.bookmarked ? 'text-primary' : 'text-fg-soft hover:text-fg'
            )}
          >
            <BookmarkIcon
              width="20"
              height="20"
              fill={post.viewer?.bookmarked ? 'currentColor' : 'none'}
            />
            {post.viewer?.bookmarked ? M.saved : M.save}
          </button>
          <Button
            variant="icon"
            label={M.more}
            onClick={() => setOpen('more')}
            className="ms-auto size-12"
          >
            <MoreIcon />
          </Button>
        </div>
        {note === null ? null : (
          <p role="status" className="m-0 flex flex-wrap items-center gap-x-3 text-fg-soft text-sm">
            {note}
            {access === 'guest' ? (
              <Link
                href={signInHref(pathname)}
                className="font-medium text-link underline-offset-4 hover:underline"
              >
                {C.signIn}
              </Link>
            ) : null}
          </p>
        )}
        {failure === null ? null : (
          <div role="alert">
            <Notice tone="error">{failure}</Notice>
          </div>
        )}
      </footer>

      {post.why === null ? null : (
        <WhySheet why={post.why} open={open === 'why'} onClose={closeSheets} />
      )}
      <Sheet open={open === 'more'} onClose={closeSheets} title={M.more}>
        <ul className="m-0 flex list-none flex-col gap-1 p-0 pb-2">
          {isAuthor ? (
            <li>
              <Button
                variant="ghost"
                onClick={() => setOpen('withdraw')}
                className="w-full justify-start"
              >
                {post.status === 'draft' ? C.publish.withdrawDraft : C.publish.withdraw}
              </Button>
            </li>
          ) : (
            <>
              <li>
                <Button
                  variant="ghost"
                  onClick={() => setOpen('report')}
                  className="w-full justify-start"
                >
                  {C.report.action}
                </Button>
              </li>
              {access === 'guest' || access === 'unknown' ? null : (
                <li>
                  <Button
                    variant="ghost"
                    onClick={() => setOpen('block')}
                    className="w-full justify-start"
                  >
                    {C.block.action} {memberLabel(post.author)}
                  </Button>
                </li>
              )}
            </>
          )}
        </ul>
      </Sheet>
      <ReportSheet
        open={open === 'report'}
        onClose={closeSheets}
        targetType="post"
        targetId={post.id}
      />
      <BlockSheet
        open={open === 'block'}
        onClose={closeSheets}
        handle={post.author.handle}
        publicName={memberLabel(post.author)}
        onBlocked={() => onRemoved?.('blocked')}
      />
      <WithdrawSheet
        open={open === 'withdraw'}
        onClose={closeSheets}
        postId={post.id}
        onWithdrawn={() => {
          closeSheets();
          onRemoved?.('withdrawn');
        }}
      />
    </GlassPanel>
  );
}
