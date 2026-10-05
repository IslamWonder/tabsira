import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { forgetSession } from '@/account/session';
import { messages } from '@/messages';
import { forgetIdentity } from '@/social/identity-store';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY, PROFILE } from '@/test/social';
import { FollowAuthor } from './follow-author';
import { FollowToggle } from './follow-toggle';

const P = messages.community.profile;

afterEach(() => {
  forgetSession();
  forgetIdentity();
});

function reader(profile: unknown, user = USER) {
  return mockApi({
    'GET /auth/me': { body: user },
    'GET /me/public-identity': { body: IDENTITY },
    'GET /u/rain_reader': profile === 'error' ? apiError(500, 'INTERNAL') : { body: profile },
    'PUT /u/rain_reader/follow': { status: 204 },
  });
}

describe('FollowAuthor', () => {
  it('offers a signed-in reader to follow the author of a public insight, by their own tap', async () => {
    const api = reader({ ...PROFILE, viewer: { follows: false, is_self: false } });
    render(<FollowAuthor handle="rain_reader" />);
    const button = await screen.findByRole('button', { name: P.follow });
    // A visit follows nobody: nothing was sent before the tap.
    expect(await api.bodies('PUT', '/u/rain_reader/follow')).toEqual([]);
    await userEvent.click(button);
    expect(await screen.findByRole('button', { name: P.following })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('shows nothing to a guest, to the author, or when the profile cannot be read', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    const guest = render(<FollowAuthor handle="rain_reader" />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(guest.container).toBeEmptyDOMElement();
    guest.unmount();
    forgetSession();

    const self = reader({ ...PROFILE, viewer: { follows: false, is_self: true } });
    const own = render(<FollowAuthor handle="rain_reader" />);
    await waitFor(() =>
      expect(self.requests.some((request) => request.url.includes('/u/rain_reader'))).toBe(true)
    );
    expect(own.container).toBeEmptyDOMElement();
    own.unmount();
    forgetSession();

    const broken = reader('error');
    const failed = render(<FollowAuthor handle="rain_reader" />);
    await waitFor(() =>
      expect(broken.requests.some((request) => request.url.includes('/u/rain_reader'))).toBe(true)
    );
    failed.unmount();
    expect(failed.container).toBeEmptyDOMElement();
  });
});

describe('FollowToggle, compact', () => {
  it('stays out of the way of a guest and of an unverified account', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    const guest = render(
      <FollowToggle handle="rain_reader" follows={false} onChange={() => undefined} compact />
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(guest.container).toBeEmptyDOMElement();
    guest.unmount();
    forgetSession();

    reader(PROFILE, { ...USER, email_verified: false });
    const unverified = render(
      <FollowToggle handle="rain_reader" follows={false} onChange={() => undefined} compact />
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(unverified.container).toBeEmptyDOMElement();
  });
});
