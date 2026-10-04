import type { Route } from 'next';
import { AtlasIcon, CameraIcon, CommunityIcon, ProfileIcon, WorldIcon } from '@/components/icons';
import { ar } from '@/messages/ar';

export interface NavItem {
  href: Route;
  label: string;
  Icon: typeof WorldIcon;
}

/** The four sections, in reading order; the phone bar puts capture between the second and third. */
export const SECTIONS: readonly NavItem[] = [
  { href: '/world', label: ar.nav.world, Icon: WorldIcon },
  { href: '/community', label: ar.nav.community, Icon: CommunityIcon },
  { href: '/atlas', label: ar.nav.atlas, Icon: AtlasIcon },
  { href: '/me', label: ar.nav.me, Icon: ProfileIcon },
];

export const CAPTURE: NavItem = { href: '/', label: ar.nav.capture, Icon: CameraIcon };

export function isActive(href: string, pathname: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}
