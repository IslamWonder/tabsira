'use client';

import Link from 'next/link';
import { useCallback, useEffect, useId, useState } from 'react';
import { signInHref } from '@/account/links';
import { useSession } from '@/account/session';
import { StatusScreen } from '@/components/app/status-screen';
import { CommunityIcon, MoreIcon } from '@/components/icons';
import { PageContainer } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages, siteLanguage } from '@/messages';
import { useAccess } from '@/social/access';
import { getProfile, memberPosts, setFollow } from '@/social/api';
import { memberLabel, profilePath } from '@/social/identity';
import type { MemberProfile, Post } from '@/social/types';
import { usePages } from '@/social/use-pages';
import { FeedList } from './feed-list';
import { BlockSheet } from './sheets';

const P = messages.community.profile;
const C = messages.community;

type Load =
  | { kind: 'loading' }
  | { kind: 'ready'; profile: MemberProfile }
  | { kind: 'missing' }
  | { kind: 'blocked' }
  | { kind: 'failed'; failure: Failure };

/** `YYYY-MM` as a month name and a year in the site's language, Western digits. */
export function formatMonth(joined: string): string {
  const [year, month] = joined.split('-').map(Number);
  /* v8 ignore next 3: `year` is never undefined, split always yields a first part; the fallback only satisfies the index type */
  return new Intl.DateTimeFormat(siteLanguage.intl, { month: 'long', year: 'numeric' }).format(
    new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, 1))
  );
}

function Counts({ profile }: { profile: MemberProfile }) {
  const counts = [
    [P.counts.posts, profile.posts_count],
    [P.counts.followers, profile.followers_count],
    [P.counts.following, profile.following_count],
  ] as const;
  return (
    <dl className="m-0 flex flex-wrap gap-x-6 gap-y-1">
      {counts.map(([label, count]) => (
        <div key={label} className="flex items-baseline gap-1.5">
          <dd className="m-0 font-semibold text-fg tabular-nums">{count}</dd>
          <dt className="text-[0.875rem] text-fg-muted">{label}</dt>
        </div>
      ))}
    </dl>
  );
}

function FollowButton({
  profile,
  onChange,
}: {
  profile: MemberProfile;
  onChange: (profile: MemberProfile) => void;
}) {
  const access = useAccess();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const follows = profile.viewer?.follows === true;
  if (access === 'guest') {
    return (
      <LinkButton href={signInHref(profilePath(profile.handle))} variant="secondary">
        {P.signIn}
      </LinkButton>
    );
  }
  if (access === 'unverified' && !follows) {
    return <p className="m-0 text-fg-soft text-sm">{P.verify}</p>;
  }
  const toggle = async () => {
    setBusy(true);
    setFailure(null);
    const result = await setFollow(profile.handle, !follows);
    setBusy(false);
    if (result.ok) {
      onChange({
        ...profile,
        followers_count: profile.followers_count + (follows ? -1 : 1),
        viewer: { follows: !follows, is_self: false },
      });
    } else {
      setFailure(failureMessage(result));
    }
  };
  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        variant={follows ? 'secondary' : 'primary'}
        aria-pressed={follows}
        onClick={toggle}
        disabled={busy || access === 'unknown'}
      >
        {follows ? P.following : P.follow}
      </Button>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
    </div>
  );
}

/**
 * A public profile: the two things a member chose to be known by, the month
 * they joined and three counts, then their published posts the viewer may
 * read (docs/SOCIAL_NETWORK.md «Public profile»). Nothing else about the
 * person exists in the answer, so nothing else is shown.
 */
export function ProfileScreen({ handle }: { handle: string }) {
  const session = useSession();
  const headingId = useId();
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [open, setOpen] = useState<'none' | 'more' | 'block'>('none');
  const sessionStatus = session.status;
  // Counts the retries: each one asks the API again.
  const [attempt, setAttempt] = useState(0);

  // Asked again when the session changes (what the viewer may see depends on who they are)
  // and on every retry.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` counts the retries; each one asks again.
  useEffect(() => {
    if (sessionStatus === 'unknown') {
      return;
    }
    let current = true;
    setLoad({ kind: 'loading' });
    void getProfile(handle).then((result) => {
      if (!current) {
        return;
      }
      if (result.ok) {
        setLoad({ kind: 'ready', profile: result.data });
      } else {
        setLoad(result.status === 404 ? { kind: 'missing' } : { kind: 'failed', failure: result });
      }
    });
    return () => {
      current = false;
    };
  }, [handle, sessionStatus, attempt]);

  const fetchPage = useCallback((cursor: string | null) => memberPosts(handle, cursor), [handle]);
  const pages = usePages<Post>(
    fetchPage,
    `member:${handle}:${session.status}`,
    session.status !== 'unknown'
  );
  const isSelf = load.kind === 'ready' && load.profile.viewer?.is_self === true;

  return (
    <PageContainer className="flex max-w-[48rem] flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-6 tablet:pb-10">
      <Link
        href="/community"
        className="inline-flex min-h-10 items-center self-start text-link underline-offset-4 hover:underline"
      >
        {C.back}
      </Link>
      {load.kind === 'loading' ? (
        <p role="status" className="m-0 py-8 text-center text-fg-muted">
          {P.loading}
        </p>
      ) : null}
      {load.kind === 'ready' ? (
        <>
          <GlassPanel
            as="section"
            ornate
            aria-labelledby={headingId}
            className="flex flex-col gap-4 tablet:p-7"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-1">
                <h1
                  id={headingId}
                  className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg"
                >
                  {load.profile.public_name ?? <bdi>@{load.profile.handle}</bdi>}
                </h1>
                {load.profile.public_name === null ? null : (
                  <bdi className="text-fg-muted">@{load.profile.handle}</bdi>
                )}
                <p className="m-0 text-[0.875rem] text-fg-muted">
                  {P.joined(formatMonth(load.profile.joined_month))}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {isSelf ? (
                  <LinkButton href="/me#identity" variant="secondary">
                    {P.edit}
                  </LinkButton>
                ) : (
                  <>
                    <FollowButton
                      profile={load.profile}
                      onChange={(profile) => setLoad({ kind: 'ready', profile })}
                    />
                    {session.status === 'signed-in' ? (
                      <Button variant="icon" label={C.post.more} onClick={() => setOpen('more')}>
                        <MoreIcon />
                      </Button>
                    ) : null}
                  </>
                )}
              </div>
            </div>
            <Counts profile={load.profile} />
            {isSelf ? <p className="m-0 text-[0.875rem] text-fg-muted">{P.you}</p> : null}
          </GlassPanel>
          <section aria-label={P.posts} className="flex flex-col gap-4">
            <h2 className="m-0 font-semibold text-subheading text-fg">{P.posts}</h2>
            <FeedList
              pages={pages}
              emptyText={() => P.noPosts}
              headingLevel={3}
              onAuthorBlocked={(blocked) => {
                if (blocked === handle) {
                  setLoad({ kind: 'blocked' });
                }
              }}
            />
          </section>
          <Sheet open={open === 'more'} onClose={() => setOpen('none')} title={C.post.more}>
            <ul className="m-0 flex list-none flex-col gap-1 p-0 pb-2">
              <li>
                <Button
                  variant="ghost"
                  onClick={() => setOpen('block')}
                  className="w-full justify-start"
                >
                  {C.block.action} {memberLabel(load.profile)}
                </Button>
              </li>
            </ul>
          </Sheet>
          <BlockSheet
            open={open === 'block'}
            onClose={() => setOpen('none')}
            handle={load.profile.handle}
            publicName={memberLabel(load.profile)}
            onBlocked={() => setLoad({ kind: 'blocked' })}
          />
        </>
      ) : null}
      {load.kind === 'blocked' ? (
        <div role="status" className="flex flex-col items-start gap-4">
          <Notice tone="success">{C.block.blocked}</Notice>
          <LinkButton href="/community" variant="secondary">
            {C.back}
          </LinkButton>
        </div>
      ) : null}
      {load.kind === 'missing' ? (
        <StatusScreen
          icon={<CommunityIcon width="28" height="28" />}
          title={P.notFound.title}
          description={P.notFound.description}
          className="py-10"
        >
          <LinkButton href="/community" variant="secondary">
            {C.back}
          </LinkButton>
        </StatusScreen>
      ) : null}
      {load.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{failureMessage(load.failure)}</Notice>
          <Button variant="ghost" onClick={() => setAttempt((count) => count + 1)}>
            {C.retry}
          </Button>
        </div>
      ) : null}
    </PageContainer>
  );
}
