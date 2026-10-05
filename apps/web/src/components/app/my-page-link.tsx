'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ProfileIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { profilePath } from '@/social/identity';
import { hasIdentity, useIdentity } from '@/social/identity-store';

/**
 * The top bar's way to one's own public page, the page others follow and the
 * one to share. Shown once the member has chosen a handle; before that, the profile page
 * in the navigation is where the handle is chosen.
 */
export function MyPageLink() {
  const identity = useIdentity();
  const pathname = usePathname();
  if (!hasIdentity(identity)) {
    return null;
  }
  const href = profilePath(identity.identity.handle) as Route;
  const current = pathname === href;
  return (
    <Link
      href={href}
      aria-label={messages.nav.myPageLabel(identity.identity.handle)}
      aria-current={current ? 'page' : undefined}
      className={cx(
        'inline-flex min-h-10 items-center gap-2 whitespace-nowrap rounded-full px-3 text-sm transition-colors duration-200',
        current
          ? 'bg-[var(--chip-primary-bg)] font-semibold text-[var(--chip-primary-fg)]'
          : 'text-glass-fg-soft hover:text-glass-fg'
      )}
    >
      <ProfileIcon width="18" height="18" aria-hidden="true" />
      {messages.nav.myPage}
    </Link>
  );
}
