'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSession } from '@/account/session';
import { useCapture } from '@/components/capture/capture-provider';
import { CameraIcon, ProfileIcon } from '@/components/icons';
import { Button, LinkButton } from '@/components/ui/button';
import { SoundToggle } from '@/components/ui/sound-toggle';
import { ThemeToggle } from '@/components/ui/theme-toggle';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { Brand } from './brand';
import { isActive, SECTIONS } from './nav-items';

/**
 * The top bar of tablets and desktops (DESIGN_DECISION.md «Responsive web
 * application»): the brand at the start, the four sections as tabs in the
 * middle, and the capture button as the one primary button at the end (Von
 * Restorff), which opens the camera wherever the reader is. It is the web's own pattern (Jakob's law); the phone keeps its
 * floating bar. Tabs change colour on hover, never size or place.
 */
export function TopBar() {
  const pathname = usePathname();
  const session = useSession();
  const capture = useCapture();
  return (
    <header className="topbar-glass sticky top-0 z-40 hidden tablet:block">
      {/* A gold rule under the bar, brightest at its middle: the edge of an RPG window. */}
      <span
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-px"
        style={{
          background: 'linear-gradient(90deg, transparent, var(--ornament), transparent)',
          opacity: 0.55,
        }}
      />
      <div className="mx-auto flex h-[var(--topbar-height)] w-full max-w-[1440px] items-center gap-4 px-6 desktop:gap-6 desktop:px-10">
        <Brand />
        <nav aria-label={messages.nav.label} className="min-w-0 flex-1">
          <ul className="flex items-center justify-center gap-1">
            {SECTIONS.map((item) => {
              const active = isActive(item.href, pathname);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? 'page' : undefined}
                    className={cx(
                      'inline-flex min-h-12 items-center gap-2 rounded-full px-4 text-[0.9375rem] transition-colors duration-200',
                      active
                        ? 'bg-[var(--chip-primary-bg)] font-semibold text-[var(--chip-primary-fg)]'
                        : 'text-glass-fg-soft hover:text-glass-fg'
                    )}
                  >
                    <item.Icon width="18" height="18" className="hidden desktop:block" />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="flex shrink-0 items-center gap-2">
          <SoundToggle />
          <ThemeToggle />
          {/* Shown until the API says someone is signed in: most visitors are guests.
              Signing in is a secondary button, never a second glowing fill (Von Restorff);
              creating an account sits beside it from desktop width, and the sign-in page
              offers it too, so a tablet loses nothing. */}
          {session.status === 'signed-in' ? null : (
            <>
              <LinkButton href="/signin" variant="secondary" current={pathname === '/signin'}>
                <ProfileIcon width="18" height="18" />
                {messages.nav.signIn}
              </LinkButton>
              <span className="hidden desktop:contents">
                <LinkButton href="/signup" variant="ghost" current={pathname === '/signup'}>
                  {messages.nav.signUp}
                </LinkButton>
              </span>
            </>
          )}
          <Button variant="cta" onClick={capture.open} aria-haspopup="dialog">
            <CameraIcon width="20" height="20" strokeWidth={2} />
            {messages.nav.captureScene}
          </Button>
        </div>
      </div>
    </header>
  );
}
