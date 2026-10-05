'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { signInHref } from '@/account/links';
import { useSession } from '@/account/session';
import { PlusIcon } from '@/components/icons';
import { FeedLayout } from '@/components/layout/layouts';
import { LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { bookmarksPage, type FeedKind, feedPage, myPostsPage } from '@/social/api';
import type { Post } from '@/social/types';
import { usePages } from '@/social/use-pages';
import { FeedList } from './feed-list';

const C = messages.community;

export type Tab = FeedKind | 'mine' | 'saved';

const PUBLIC_TABS: readonly Tab[] = ['for-you', 'following', 'latest'];
const PRIVATE_TABS: readonly Tab[] = ['mine', 'saved'];
const TAB_LABEL: Record<Tab, string> = {
  'for-you': C.tabs.forYou,
  following: C.tabs.following,
  latest: C.tabs.latest,
  mine: C.tabs.mine,
  saved: C.tabs.saved,
};
const TAB_HASH: Record<Tab, string> = {
  'for-you': '',
  following: 'following',
  latest: 'latest',
  mine: 'mine',
  saved: 'saved',
};

/** The tab named by the address's fragment, so a link can open one and the back button behaves. */
export function tabFromHash(hash: string): Tab {
  const name = hash.replace(/^#/, '');
  const found = (Object.keys(TAB_HASH) as Tab[]).find(
    (tab) => TAB_HASH[tab] === name && name !== ''
  );
  return found ?? 'for-you';
}

function emptyTextFor(tab: Tab): (reason: string | null) => string {
  if (tab === 'saved') {
    return () => C.empty.saved;
  }
  if (tab === 'mine') {
    return () => C.empty.mine;
  }
  return (reason) => (reason === 'follows_nobody' ? C.empty.follows_nobody : C.empty.no_posts);
}

function Tabs({
  tabs,
  current,
  onChange,
}: {
  tabs: readonly Tab[];
  current: Tab;
  onChange: (tab: Tab) => void;
}) {
  return (
    <div role="tablist" aria-label={C.tabsLabel} className="flex flex-wrap gap-1 desktop:flex-col">
      {tabs.map((tab) => {
        const active = tab === current;
        return (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls="community-feed"
            id={`tab-${tab}`}
            onClick={() => onChange(tab)}
            className={cx(
              'inline-flex min-h-12 items-center rounded-full px-4 text-[0.9375rem] transition-colors duration-200 desktop:justify-start',
              active
                ? 'bg-[var(--chip-primary-bg)] font-semibold text-[var(--chip-primary-fg)]'
                : 'text-fg-soft hover:bg-surface hover:text-fg'
            )}
          >
            {TAB_LABEL[tab]}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The community: the for-you feed, the following feed and the latest, and for a signed-in
 * person their own posts in every state and what they saved. On a phone the
 * tabs sit on top of the feed; on a desktop they take the side column
 * (DESIGN_DECISION.md «Responsive web application»). The ranking of the for-you feed is
 * explained on every item by the why-this button.
 */
export function CommunityScreen({ comments = false }: { comments?: boolean }) {
  const session = useSession();
  const signedIn = session.status === 'signed-in';
  const [tab, setTab] = useState<Tab>('for-you');

  useEffect(() => {
    setTab(tabFromHash(window.location.hash));
    const onHash = () => setTab(tabFromHash(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const choose = (next: Tab) => {
    setTab(next);
    const hash = TAB_HASH[next];
    window.history.replaceState(null, '', hash === '' ? window.location.pathname : `#${hash}`);
  };

  const fetchPage = useCallback(
    (cursor: string | null) => {
      if (tab === 'saved') {
        return bookmarksPage(cursor);
      }
      if (tab === 'mine') {
        return myPostsPage(cursor);
      }
      return feedPage(tab, cursor);
    },
    [tab]
  );
  // A guest's private tabs and the following feed are gated, not requested.
  const gated = !signedIn && (tab === 'following' || tab === 'mine' || tab === 'saved');
  // Nothing is asked until the session is known: what a feed holds depends on who reads it.
  const pages = usePages<Post>(
    fetchPage,
    `${tab}:${gated ? 'gated' : 'open'}:${session.status}`,
    session.status !== 'unknown' && !gated
  );

  const gate = gated ? (
    <GlassPanel className="flex flex-col items-start gap-3">
      <p className="m-0 text-fg-soft leading-[1.85]">
        {tab === 'following' ? C.signInToFollow : C.empty[tab === 'mine' ? 'mine' : 'saved']}
      </p>
      {session.status === 'guest' ? (
        <LinkButton href={signInHref('/community')} variant="secondary">
          {C.signIn}
        </LinkButton>
      ) : null}
    </GlassPanel>
  ) : undefined;

  return (
    <FeedLayout
      className="pt-[max(28px,env(safe-area-inset-top))] pb-4 tablet:pb-8"
      aside={
        <div className="flex flex-col gap-5">
          <header className="flex flex-col gap-1.5">
            <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
              {C.title}
            </h1>
            <p className="m-0 text-fg-soft leading-[1.85]">{C.lead}</p>
          </header>
          <Tabs
            tabs={signedIn ? [...PUBLIC_TABS, ...PRIVATE_TABS] : PUBLIC_TABS}
            current={tab}
            onChange={choose}
          />
          {signedIn ? (
            <div className="hidden flex-col gap-2 desktop:flex">
              <Link
                href="/community/publish"
                className="inline-flex min-h-12 items-center gap-2 self-start rounded-full border border-[var(--secondary-border)] px-5 font-medium text-[0.9375rem] text-[var(--secondary-fg)] transition-colors duration-200 hover:bg-surface"
              >
                <PlusIcon width="18" height="18" />
                {C.publishCall}
              </Link>
              <p className="m-0 text-[0.8125rem] text-fg-muted leading-[1.8]">{C.publishHint}</p>
            </div>
          ) : null}
        </div>
      }
      feed={
        <div
          id="community-feed"
          role="tabpanel"
          aria-labelledby={`tab-${tab}`}
          className="flex flex-col gap-5 pt-1 desktop:pt-0"
        >
          <FeedList pages={pages} emptyText={emptyTextFor(tab)} gate={gate} comments={comments} />
        </div>
      }
    />
  );
}
