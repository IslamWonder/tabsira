import { render, renderHook, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { forgetSession, setSignedIn } from '@/account/session';
import { forgetIdentity, setIdentity } from '@/social/identity-store';
import { mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY } from '@/test/social';
import { MyPageIcon, ProfileCornerLink, useMyPage } from './my-page-link';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

afterEach(() => {
  forgetIdentity();
  forgetSession();
  pathname.value = '/';
});

function member(handle: string | null) {
  mockApi({ 'GET /me/public-identity': { body: { ...IDENTITY, handle } } });
  setSignedIn(USER);
  setIdentity({ ...IDENTITY, handle });
}

describe('one’s own public page', () => {
  it('is known once the member has chosen a handle, and not before', () => {
    expect(renderHook(() => useMyPage()).result.current).toBeNull();
    member(null);
    expect(renderHook(() => useMyPage()).result.current).toBeNull();
    member('reader');
    expect(renderHook(() => useMyPage()).result.current).toEqual({
      href: '/u/reader',
      handle: 'reader',
    });
  });

  it('has an icon of its own, decorative', () => {
    const { container } = render(<MyPageIcon width="18" height="18" />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('ProfileCornerLink', () => {
  it('leads to «ملفي» from the corner once «صفحتي» has the tab, current on the hub and the sky', () => {
    member('reader');
    const { rerender } = render(<ProfileCornerLink />);
    const link = screen.getByRole('link', { name: 'ملفي' });
    expect(link).toHaveAttribute('href', '/me');
    expect(link).not.toHaveAttribute('aria-current');
    for (const page of ['/me', '/sky']) {
      pathname.value = page;
      rerender(<ProfileCornerLink />);
      expect(screen.getByRole('link')).toHaveAttribute('aria-current', 'page');
    }
  });

  it('is absent while «ملفي» is still the tab: a guest, or a member without a handle', () => {
    const { container, unmount } = render(<ProfileCornerLink />);
    expect(container).toBeEmptyDOMElement();
    unmount();
    member(null);
    expect(render(<ProfileCornerLink />).container).toBeEmptyDOMElement();
  });
});
