import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { ENTRY } from '@/test/atlas';
import { USER } from '@/test/fixtures';
import { type FakeSource, forgetMaps, loadedMap } from '@/test/maplibre';
import { HADITH_TEXT, IDENTITY, QURAN_TEXT, sha256 } from '@/test/social';
import { EntryScreen } from './entry-screen';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({ usePathname: () => `/atlas/entries/${ENTRY.id}` }));

afterEach(forgetMaps);

describe('EntryScreen', () => {
  it('shows the insight with its scripture byte for byte, the approximate point and its place', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: { body: ENTRY },
    });
    render(<EntryScreen entryId={ENTRY.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
    const quran = document.querySelector('[data-scripture="quran"]');
    const hadith = document.querySelector('[data-scripture="hadith"]');
    expect(quran?.textContent).toBe(QURAN_TEXT);
    expect(hadith?.textContent).toBe(HADITH_TEXT);
    expect(sha256(quran?.textContent ?? '')).toBe(ENTRY.quran[0]?.sha256);
    expect(sha256(hadith?.textContent ?? '')).toBe(ENTRY.hadith[0]?.sha256);
    expect(screen.queryByRole('link', { name: /تحقق في الدرر/ })).toBeNull();
    expect(screen.queryByText(/الدرر/)).toBeNull();
    expect(screen.getByText('[موقع تقريبي ضمن نحو 1000 م]')).toBeInTheDocument();
    expect(screen.getByText(/النقطة مركز منطقة تقريبية/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '[تونس]، [تونس البلد]' })).toHaveAttribute(
      'href',
      '/atlas/places/2464470'
    );
    expect(screen.getByRole('link', { name: '[اسم عام]' })).toHaveAttribute(
      'href',
      '/u/rain_reader'
    );
    expect(screen.getByRole('link', { name: 'افتح المنشور في تواصل' })).toHaveAttribute(
      'href',
      '/posts/7345678901234567890'
    );
    // The way to the entries sharing its meaning: the atlas filtered by the first concept.
    expect(screen.getByRole('link', { name: 'بصائر بالمعنى نفسه على الخريطة' })).toHaveAttribute(
      'href',
      '/atlas#t=rain'
    );
    const map = await loadedMap();
    expect(map.options.interactive).toBe(false);
    expect(
      ((map.getSource('marker') as FakeSource).data as { features: unknown[] }).features
    ).toHaveLength(1);
    // A guest has no report button.
    expect(screen.queryByRole('button', { name: 'بلّغ' })).toBeNull();
  });

  it('names no author, and no dot before the place, for an entry whose place was widened', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: { body: { ...ENTRY, author: null, orphaned: true } },
    });
    render(<EntryScreen entryId={ENTRY.id} />);
    await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' });
    expect(screen.queryByRole('link', { name: '[اسم عام]' })).toBeNull();
    const place = screen.getByRole('link', { name: '[تونس]، [تونس البلد]' });
    expect(place.parentElement?.textContent).toBe(place.textContent);
  });

  it('lets a member report the entry with a place reason', async () => {
    const api = mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [`GET /atlas/entries/${ENTRY.id}`]: { body: { ...ENTRY, concepts: [] } },
      'POST /reports': { status: 201, body: { id: '1' } },
    });
    render(<EntryScreen entryId={ENTRY.id} />);
    await userEvent.click(await screen.findByRole('button', { name: 'بلّغ' }));
    // An entry with no concept recorded offers no way to the same meaning.
    expect(screen.queryByRole('link', { name: 'بصائر بالمعنى نفسه على الخريطة' })).toBeNull();
    await userEvent.click(screen.getByRole('radio', { name: 'المكان غير صحيح' }));
    await userEvent.click(screen.getByRole('button', { name: 'أرسل البلاغ' }));
    expect(await screen.findByText('وصل بلاغك، وسيراجعه مشرف.')).toBeInTheDocument();
    expect(await api.bodies('POST', '/reports')).toEqual([
      { target_type: 'map_entry', target_id: ENTRY.id, reason: 'wrong_place', details: null },
    ]);
  });

  it('tells a withdrawn entry from a missing one, and retries a failed load', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: apiError(410, 'GONE'),
    });
    const { unmount } = render(<EntryScreen entryId={ENTRY.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'سُحبت هذه البصيرة أو تغيّر عنوانها' })
    ).toBeInTheDocument();
    unmount();

    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: apiError(404, 'NOT_FOUND'),
    });
    const missing = render(<EntryScreen entryId={ENTRY.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'لم نجد هذه البصيرة' })
    ).toBeInTheDocument();
    missing.unmount();

    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: 'network-error',
    });
    render(<EntryScreen entryId={ENTRY.id} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: { body: ENTRY },
    });
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
  });

  it('shows the public photo when the entry carries its address, and nothing otherwise', async () => {
    const url = 'https://media.tabsira.test/public/0123456789abcdef0123456789abcdef.jpg';
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: { body: { ...ENTRY, photo_url: url } },
    });
    const { unmount } = render(<EntryScreen entryId={ENTRY.id} />);
    expect(
      await screen.findByRole('img', {
        name: 'صورة المشهد الذي وُلدت منه البصيرة «[عنوان البصيرة]»',
      })
    ).toHaveAttribute('src', url);
    unmount();

    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: { body: ENTRY },
    });
    render(<EntryScreen entryId={ENTRY.id} />);
    await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' });
    expect(screen.queryByTestId('public-photo')).toBeNull();
  });

  it('shows an entry without a place, a step or a post, and lets the report sheet close', async () => {
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [`GET /atlas/entries/${ENTRY.id}`]: {
        body: { ...ENTRY, place: null, step: null, post_id: null },
      },
    });
    render(<EntryScreen entryId={ENTRY.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '[تونس]، [تونس البلد]' })).toBeNull();
    expect(screen.queryByText('خطوة صغيرة')).toBeNull();
    expect(screen.queryByRole('link', { name: 'افتح المنشور في تواصل' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'بلّغ' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('forgets an answer that arrives after the page left', async () => {
    let answer: (() => void) | null = null;
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /atlas/entries/${ENTRY.id}`]: () =>
        new Promise((resolve) => {
          answer = () => resolve({ body: ENTRY });
        }),
    });
    const { unmount } = render(<EntryScreen entryId={ENTRY.id} />);
    await vi.waitFor(() => expect(answer).not.toBeNull());
    unmount();
    (answer as unknown as () => void)();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
  });
});
