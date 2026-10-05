import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { forgetSession, setSignedIn } from '@/account/session';
import { messages } from '@/messages';
import { forgetIdentity, setIdentity } from '@/social/identity-store';
import { mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY } from '@/test/social';
import { MyPageLink } from './my-page-link';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

afterEach(() => {
  forgetIdentity();
  forgetSession();
  pathname.value = '/';
});

describe('MyPageLink', () => {
  it('leads a member with a handle to their public page, marked when it is the one shown', () => {
    mockApi({ 'GET /me/public-identity': { body: IDENTITY } });
    setSignedIn(USER);
    setIdentity(IDENTITY);
    const { rerender } = render(<MyPageLink />);
    const link = screen.getByRole('link', { name: messages.nav.myPageLabel('reader') });
    expect(link).toHaveAttribute('href', '/u/reader');
    expect(link).not.toHaveAttribute('aria-current');
    pathname.value = '/u/reader';
    rerender(<MyPageLink />);
    expect(screen.getByRole('link')).toHaveAttribute('aria-current', 'page');
  });

  it('is absent for a guest and for a member without a handle yet', () => {
    const { container, unmount } = render(<MyPageLink />);
    expect(container).toBeEmptyDOMElement();
    unmount();
    mockApi({ 'GET /me/public-identity': { body: { ...IDENTITY, handle: null } } });
    setSignedIn(USER);
    setIdentity({ ...IDENTITY, handle: null });
    expect(render(<MyPageLink />).container).toBeEmptyDOMElement();
  });
});
