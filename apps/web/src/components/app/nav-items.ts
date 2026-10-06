import type { Route } from 'next';
import { AtlasIcon, CameraIcon, CommunityIcon, ProfileIcon, WorldIcon } from '@/components/icons';
import { messages } from '@/messages';

export interface NavItem {
  href: Route;
  label: string;
  Icon: typeof WorldIcon;
}

/** The four sections, in reading order; the phone bar puts capture between the second and third. */
export const SECTIONS: readonly NavItem[] = [
  { href: '/world', label: messages.nav.world, Icon: WorldIcon },
  { href: '/community', label: messages.nav.community, Icon: CommunityIcon },
  { href: '/atlas', label: messages.nav.atlas, Icon: AtlasIcon },
  { href: '/me', label: messages.nav.me, Icon: ProfileIcon },
];

/** Capture is an action, not a page: it opens the capture sheet wherever the reader is. */
export const CAPTURE: Omit<NavItem, 'href'> = { label: messages.nav.capture, Icon: CameraIcon };

/** Pages that belong to a section without living under its path: the practice page is the profile hub's. */
const ALSO: Readonly<Record<string, string>> = { '/me': '/sky' };

function under(href: string, pathname: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function isActive(href: string, pathname: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }
  const also = ALSO[href];
  return under(href, pathname) || (also !== undefined && under(also, pathname));
}
