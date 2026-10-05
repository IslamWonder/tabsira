'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { openConsentSettings } from '@/consent/store';
import { messages } from '@/messages';

const QUIET =
  'inline-flex min-h-12 items-center text-fg-soft text-sm underline-offset-4 transition-colors duration-200 hover:text-fg hover:underline';
const EXPLORE = [
  ['/#how', messages.landing.nav.how],
  ['/#features', messages.landing.nav.features],
  ['/#example', messages.landing.nav.example],
] as const;
const PAGES = [
  ['/support', messages.footer.support],
  ['/terms', messages.footer.terms],
  ['/privacy', messages.footer.privacy],
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
  if (pathname === '/world') {
    return null;
  }
  return (
    <footer className="mx-auto w-full max-w-[1440px] px-4 pt-4 pb-nav tablet:px-6 tablet:pb-6 desktop:px-10">
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
          {EXPLORE.map(([href, label]) => (
            <li key={href}>
              <Link href={href as Route} className={QUIET}>
                {label}
              </Link>
            </li>
          ))}
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
