'use client';

import Link from 'next/link';
import { openConsentSettings } from '@/consent/store';
import { messages } from '@/messages';

const QUIET =
  'inline-flex min-h-12 items-center text-fg-soft text-sm underline-offset-4 transition-colors duration-200 hover:text-fg hover:underline';
const PAGES = [
  ['/terms', messages.footer.terms],
  ['/privacy', messages.footer.privacy],
  ['/support', messages.footer.support],
] as const;

/**
 * The foot of every page: the terms, the privacy policy, support, and the way
 * back to the cookie choice, as decision 32 and docs/SEO.md §6 ask. On a phone
 * it ends above the floating navigation. The cookie choice opens a dialog, so
 * it is a button that says so, styled as a quiet link.
 */
export function SiteFooter() {
  return (
    <footer className="mx-auto w-full max-w-[1440px] px-4 pt-4 pb-nav tablet:px-6 tablet:pb-6 desktop:px-10">
      <nav aria-label={messages.footer.label} className="border-line border-t pt-2">
        <ul className="m-0 flex list-none flex-wrap items-center justify-center gap-x-6 p-0 tablet:justify-start">
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
        </ul>
      </nav>
    </footer>
  );
}
