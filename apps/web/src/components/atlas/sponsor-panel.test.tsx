import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AtlasEntry } from '@/atlas/types';
import { messages } from '@/messages';
import { apiError, mockApi, type Reply, type Route } from '@/test/api';
import { ORPHAN_ENTRY, SPONSOR, SPONSORED_ENTRY, SPONSORSHIP } from '@/test/atlas';
import { USER } from '@/test/fixtures';
import { forgetMaps } from '@/test/maplibre';
import { IDENTITY, NO_IDENTITY } from '@/test/social';
import { EntryScreen } from './entry-screen';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({ usePathname: () => `/atlas/entries/${ORPHAN_ENTRY.id}` }));

afterEach(forgetMaps);

const S = messages.atlas.sponsor;
const ID = ORPHAN_ENTRY.id;
const ENTRY_PATH = `GET /atlas/entries/${ID}`;
const SPONSORSHIP_PATH = `/atlas/entries/${ID}/sponsorship`;
const ME = { handle: IDENTITY.handle, public_name: IDENTITY.public_name };

/** An entry route that answers each time with the next entry of the list (the last one repeats). */
function entries(...bodies: AtlasEntry[]): Route {
  let asked = 0;
  return (): Reply => ({ body: bodies[Math.min(asked++, bodies.length - 1)] });
}

const member = (extra: Record<string, Route> = {}) =>
  mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: IDENTITY },
    [ENTRY_PATH]: { body: ORPHAN_ENTRY },
    ...extra,
  });

async function open(props: { sponsorship?: boolean; social?: boolean } = {}) {
  render(
    <EntryScreen entryId={ID} sponsorship={props.sponsorship ?? true} social={props.social} />
  );
  await screen.findByRole('heading', { level: 1 });
}

describe('the sponsoring part of an entry page', () => {
  it('shows nothing of it while the feature is off, and no author for a widened entry', async () => {
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [ENTRY_PATH]: { body: SPONSORED_ENTRY },
    });
    await open({ sponsorship: false });
    expect(screen.queryByRole('region', { name: S.entry.section })).toBeNull();
    expect(screen.queryByText(S.entry.by)).toBeNull();
    expect(screen.queryByRole('button', { name: S.entry.action })).toBeNull();
  });

  it('shows nothing for an entry that is neither orphaned nor sponsored', async () => {
    member({ [ENTRY_PATH]: { body: { ...ORPHAN_ENTRY, orphaned: false } } });
    await open();
    expect(screen.queryByRole('region', { name: S.entry.section })).toBeNull();
  });

  it('sends a guest to sign in and offers no button', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [ENTRY_PATH]: { body: ORPHAN_ENTRY },
    });
    await open();
    const section = screen.getByRole('region', { name: S.entry.section });
    expect(within(section).getByText(S.entry.waitingLead)).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      expect.stringContaining('/signin')
    );
    expect(within(section).queryByRole('button', { name: S.entry.action })).toBeNull();
    expect(screen.queryByText(/@/)).toBeNull();
  });

  it('asks an unverified account to verify first', async () => {
    mockApi({
      'GET /auth/me': { body: { ...USER, email_verified: false } },
      [ENTRY_PATH]: { body: ORPHAN_ENTRY },
    });
    render(<EntryScreen entryId={ID} sponsorship />);
    expect(await screen.findByText(S.entry.verify)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: S.entry.action })).toBeNull();
  });

  it('asks a member without a public identity to choose one first', async () => {
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: NO_IDENTITY },
      [ENTRY_PATH]: { body: ORPHAN_ENTRY },
    });
    render(<EntryScreen entryId={ID} sponsorship />);
    expect(await screen.findByText(S.entry.identityFirst)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: S.entry.action })).toBeNull();
  });

  it('sponsors for a verified member, then shows who looks after it and the sponsor controls', async () => {
    const api = member({
      [ENTRY_PATH]: entries(ORPHAN_ENTRY, {
        ...SPONSORED_ENTRY,
        sponsor: ME,
        sponsor_reflection: null,
      }),
      [`PUT ${SPONSORSHIP_PATH}`]: { body: SPONSORSHIP },
    });
    await open();
    await userEvent.click(screen.getByRole('button', { name: S.entry.action }));
    expect(await screen.findByText(S.entry.sponsored)).toBeInTheDocument();
    expect(api.requests.some((r) => r.method === 'PUT' && r.url.endsWith(SPONSORSHIP_PATH))).toBe(
      true
    );
    expect(screen.getByText(S.entry.by)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /\[قارئ\]/ })).toHaveAttribute('href', '/u/reader');
    // The entry still names no author.
    expect(screen.queryByRole('link', { name: '[اسم عام]' })).toBeNull();
  });

  const refusals: [string, Reply, AtlasEntry, string][] = [
    ['own entry', apiError(409, 'CONFLICT'), ORPHAN_ENTRY, S.refusal.own],
    [
      'already sponsored',
      apiError(409, 'CONFLICT'),
      { ...SPONSORED_ENTRY, orphaned: true },
      S.refusal.already,
    ],
    [
      'not orphaned',
      apiError(409, 'CONFLICT'),
      { ...ORPHAN_ENTRY, orphaned: false },
      S.refusal.notOrphaned,
    ],
    ['under 13', apiError(409, 'UNDER_13_CANNOT_PUBLISH'), ORPHAN_ENTRY, S.refusal.under13],
    [
      'public identity',
      apiError(409, 'PUBLIC_IDENTITY_REQUIRED'),
      ORPHAN_ENTRY,
      S.refusal.identity,
    ],
    ['unverified', apiError(403, 'FORBIDDEN'), ORPHAN_ENTRY, S.refusal.verify],
    ['unavailable', apiError(404, 'NOT_FOUND'), ORPHAN_ENTRY, S.refusal.unavailable],
    ['anything else', apiError(503, 'SERVICE_UNAVAILABLE'), ORPHAN_ENTRY, messages.errors.server],
  ];
  it.each(refusals)(
    'says %s in Arabic from the messages module',
    async (_name, reply, fresh, message) => {
      member({
        [ENTRY_PATH]: entries(ORPHAN_ENTRY, fresh),
        [`PUT ${SPONSORSHIP_PATH}`]: reply,
      });
      await open();
      await userEvent.click(screen.getByRole('button', { name: S.entry.action }));
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      if (message === S.refusal.identity) {
        expect(
          screen.getByRole('link', { name: messages.community.comments.chooseIdentity })
        ).toHaveAttribute('href', '/me#identity');
      }
    }
  );

  it('answers a conflict with the unavailable sentence when the entry cannot be read again', async () => {
    let asked = 0;
    member({
      [ENTRY_PATH]: () =>
        asked++ === 0 ? { body: ORPHAN_ENTRY } : apiError(503, 'SERVICE_UNAVAILABLE'),
      [`PUT ${SPONSORSHIP_PATH}`]: apiError(409, 'CONFLICT'),
    });
    await open();
    await userEvent.click(screen.getByRole('button', { name: S.entry.action }));
    expect(await screen.findByRole('alert')).toHaveTextContent(S.refusal.unavailable);
  });

  it('names another member as sponsor with a link while the network is on, plain text otherwise', async () => {
    member({ [ENTRY_PATH]: { body: SPONSORED_ENTRY } });
    const { unmount } = render(<EntryScreen entryId={ID} sponsorship />);
    const link = await screen.findByRole('link', { name: /\[اسم الكافل\]/ });
    expect(link).toHaveAttribute('href', `/u/${SPONSOR.handle}`);
    expect(link).toHaveTextContent('@quiet_keeper');
    expect(screen.getByText('[تأمل الكافل]')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(S.entry.reflectionNote))).toBeInTheDocument();
    // Another member's entry: no controls, and no author line.
    expect(screen.queryByRole('button', { name: S.entry.action })).toBeNull();
    unmount();

    member({ [ENTRY_PATH]: { body: SPONSORED_ENTRY } });
    render(<EntryScreen entryId={ID} sponsorship social={false} />);
    await screen.findByText(S.entry.by);
    expect(screen.queryByRole('link', { name: /\[اسم الكافل\]/ })).toBeNull();
    expect(screen.getByText(/@quiet_keeper/)).toBeInTheDocument();
  });

  it('shows no points, counts or reward wording on a sponsored entry', async () => {
    member({ [ENTRY_PATH]: { body: { ...SPONSORED_ENTRY, sponsor: ME } } });
    await open();
    const section = await screen.findByRole('region', { name: S.entry.section });
    expect(section.textContent).not.toMatch(/أجر|حسنات|نقاط|مستوى/);
  });

  it('breaks nothing when the feature is off and the entry comes as a plain widened one', async () => {
    const {
      orphaned: _o,
      sponsor: _s,
      sponsor_reflection: _r,
      sponsor_reflection_id: _i,
      ...plain
    } = {
      ...ORPHAN_ENTRY,
      sponsor: undefined,
      sponsor_reflection: undefined,
      sponsor_reflection_id: undefined,
    };
    member({ [ENTRY_PATH]: { body: plain } });
    await open();
    expect(screen.queryByRole('region', { name: S.entry.section })).toBeNull();
    cleanup();
    member({ [ENTRY_PATH]: { body: plain } });
    render(<EntryScreen entryId={ID} sponsorship />);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: S.entry.section })).toBeNull();
  });
});
