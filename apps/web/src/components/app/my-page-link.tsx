'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ProfileIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { profilePath } from '@/social/identity';
import { hasIdentity, useIdentity } from '@/social/identity-store';
import { isActive } from './nav-items';

/** One's own public page, once the member has chosen a handle; null before that. */
export function useMyPage(): { href: Route; handle: string } | null {
  const identity = useIdentity();
  if (!hasIdentity(identity)) {
    return null;
  }
  const { handle } = identity.identity;
  return { href: profilePath(handle) as Route, handle };
}

/**
 * The top bar's corner way to the profile hub, the private hub of the account and its
 * settings, where web apps keep the account (Jakob's law). Shown once the member
 * has a public page: the "my page" link then takes the fourth tab. Before that, the profile hub is
 * the tab itself, where the handle is chosen.
 */
export function ProfileCornerLink() {
  const myPage = useMyPage();
  const pathname = usePathname();
  if (myPage === null) {
    return null;
  }
  const current = isActive('/me', pathname);
  return (
    <Link
      href="/me"
      aria-current={current ? 'page' : undefined}
      className={cx(
        'inline-flex min-h-10 items-center gap-2 whitespace-nowrap rounded-full px-3 text-sm transition-colors duration-200',
        current
          ? 'bg-[var(--chip-primary-bg)] font-semibold text-[var(--chip-primary-fg)]'
          : 'text-glass-fg-soft hover:text-glass-fg'
      )}
    >
      <ProfileIcon width="18" height="18" />
      {messages.nav.me}
    </Link>
  );
}
