'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { tutorialOffered, useSession } from '@/account/session';
import { LogoMark } from '@/components/brand/logo';
import { openConsentSettings } from '@/consent/store';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

const QUIET =
  'inline-flex min-h-12 items-center text-fg-soft text-sm underline-offset-4 transition-colors duration-200 hover:text-fg hover:underline';
const EXAMPLE = '/#example';
const EXPLORE = [
  ['/#how', messages.landing.nav.how],
  ['/#features', messages.landing.nav.features],
  [EXAMPLE, messages.landing.nav.example],
] as const;
const PAGES = [
  ['/support', messages.footer.support],
  ['/terms', messages.footer.terms],
  ['/privacy', messages.footer.privacy],
  ['/sources', messages.footer.sources],
] as const;

function Column({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <h2 className="m-0 font-semibold text-[0.9375rem] text-fg">{title}</h2>
      <ul className="m-0 flex list-none flex-col p-0">{children}</ul>
    </div>
  );
}

/**
 * The foot of every page, part of its flow: the mark, the landing page's
 * sections, and support, the terms, the privacy policy and the way back to the
 * cookie choice, as decision 32 and docs/SEO.md §6 ask. On a phone it ends
 * above the floating navigation. The cookie choice opens a dialog, so it is a
 * button that says so, styled as a quiet link. The world fills the screen with
 * nothing under it (decision 59): its help panel holds these links instead.
 */
export function SiteFooter() {
  const pathname = usePathname();
  const session = useSession();
  if (pathname === '/world') {
    return null;
  }
  // The analysis is a full-screen view from tablet up, like the world: its photo and its
  // panel fill the window, and a footer under them would only add a scroll. On a phone the
  // page scrolls anyway, and the footer stays.
  const fullScreen = pathname.startsWith('/scan/');
  return (
    <footer
      className={cx(
        'mx-auto w-full max-w-[1440px] px-4 pt-4 pb-nav tablet:px-6 tablet:pb-6 desktop:px-10',
        fullScreen && 'tablet:hidden'
      )}
    >
      <nav
        aria-label={messages.footer.label}
        className="grid gap-6 border-line border-t pt-6 tablet:grid-cols-3"
      >
        <div className="flex flex-col gap-2">
          <LogoMark className="h-11" />
          <p className="m-0 max-w-[18rem] text-fg-soft text-sm leading-[1.8]">
            {messages.meta.shortDescription}
          </p>
        </div>
        <Column title={messages.footer.explore}>
          {EXPLORE.filter(([href]) => href !== EXAMPLE || tutorialOffered(session)).map(
            ([href, label]) => (
              <li key={href}>
                <Link href={href as Route} className={QUIET}>
                  {label}
                </Link>
              </li>
            )
          )}
        </Column>
        <Column title={messages.footer.help}>
          {PAGES.map(([href, label]) => (
            <li key={href}>
              <Link href={href} className={QUIET}>
                {label}
              </Link>
            </li>
          ))}
          <li>
            <button
              type="button"
              aria-haspopup="dialog"
              onClick={openConsentSettings}
              className={QUIET}
            >
              {messages.footer.cookieSettings}
            </button>
          </li>
        </Column>
      </nav>
    </footer>
  );
}
