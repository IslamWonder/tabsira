'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCapture } from '@/components/capture/capture-provider';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { CAPTURE, isActive, type NavItem, SECTIONS } from './nav-items';

// Jakob's law: five tabs at the bottom, as in every app people already use.
// Serial position: the two places people return to most sit at the ends
// (the world first, the profile last) and capture sits in the middle, under the thumb.
const SIDE_START = SECTIONS.slice(0, 2);
const SIDE_END = SECTIONS.slice(2);

function Tab({ item, pathname }: Readonly<{ item: NavItem; pathname: string }>) {
  const active = isActive(item.href, pathname);
  return (
    <li className="flex justify-center">
      <Link
        href={item.href}
        aria-current={active ? 'page' : undefined}
        className={cx(
          'relative flex h-14 w-full min-w-12 flex-col items-center justify-center gap-0.5 rounded-full text-[0.75rem] transition-colors duration-200',
          active ? 'font-semibold text-nav-active' : 'text-glass-fg-soft hover:text-glass-fg'
        )}
      >
        <item.Icon strokeWidth={active ? 2 : 1.6} />
        <span>{item.label}</span>
        {active ? (
          <span
            aria-hidden="true"
            className="absolute top-1 size-1 rounded-full bg-current shadow-[0_0_8px_currentColor]"
          />
        ) : null}
      </Link>
    </li>
  );
}

/**
 * The floating pill navigation of direction C, on phones only (from tablet up
 * the top bar takes over). Capture is the one glowing control in the bar (Von
 * Restorff) and the largest target at the bottom centre (Fitts). The bar
 * floats above the safe area, and html's scroll-padding keeps focused content
 * clear of it (WCAG 2.4.11).
 */
export function AppNav() {
  const pathname = usePathname();
  const capture = useCapture();

  return (
    <nav
      aria-label={messages.nav.label}
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[var(--nav-gap)] tablet:hidden"
    >
      <ul className="nav-glass pointer-events-auto grid h-[var(--nav-height)] w-full max-w-md grid-cols-5 items-center rounded-full px-1">
        {SIDE_START.map((item) => (
          <Tab key={item.href} item={item} pathname={pathname} />
        ))}
        <li className="flex justify-center">
          {/* An action, not a page: it opens the camera over whatever is on screen. */}
          <button
            type="button"
            onClick={capture.open}
            aria-haspopup="dialog"
            className="flex size-16 items-center justify-center rounded-full"
          >
            <span className="capture-orb flex size-[54px] items-center justify-center rounded-full">
              <CAPTURE.Icon width="24" height="24" strokeWidth={2} />
            </span>
            <span className="sr-only">{CAPTURE.label}</span>
          </button>
        </li>
        {SIDE_END.map((item) => (
          <Tab key={item.href} item={item} pathname={pathname} />
        ))}
      </ul>
    </nav>
  );
}
