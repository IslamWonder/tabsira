import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { FEATURE, PLACE_PAGE, SECOND_FEATURE } from '@/test/atlas';
import { forgetMaps, loadedMap } from '@/test/maplibre';
import { PlaceScreen } from './place-screen';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({ usePathname: () => '/atlas/places/2464470' }));

afterEach(forgetMaps);

describe('PlaceScreen', () => {
  it('names the place, lists its entries, opens one and loads the next page', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /atlas/places/2464470': (request) =>
        new URL(request.url).searchParams.get('cursor') === 'c1'
          ? { body: { ...PLACE_PAGE, entries: [SECOND_FEATURE], next_cursor: null } }
          : { body: { ...PLACE_PAGE, next_cursor: 'c1' } },
    });
    render(<PlaceScreen geonameId={2464470} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'ذاكرة المكان: [تونس]' })
    ).toBeInTheDocument();
    expect(screen.getByText('[ولاية تونس]، [تونس البلد]')).toBeInTheDocument();
    const map = await loadedMap();
    expect(map.options.center).toEqual([10.1657, 36.8189]);
    await userEvent.click(screen.getByRole('button', { name: /\[عنوان البصيرة\]/ }));
    expect(screen.getByRole('link', { name: 'افتح البصيرة' })).toHaveAttribute(
      'href',
      `/atlas/entries/${FEATURE.id}`
    );
    await userEvent.click(screen.getByRole('button', { name: 'اعرض المزيد' }));
    expect(await screen.findByRole('button', { name: /\[بصيرة ثانية\]/ })).toBeInTheDocument();
    expect(screen.getByText(/هذا كل ما نُشر في هذا المكان/)).toBeInTheDocument();
  });

  it('says when a place has nothing yet, and retries a failed load', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /atlas/places/999': apiError(404, 'NOT_FOUND'),
    });
    const { unmount } = render(<PlaceScreen geonameId={999} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'لا بصائر في هذا المكان بعد' })
    ).toBeInTheDocument();
    unmount();

    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /atlas/places/2464470': 'network-error',
    });
    render(<PlaceScreen geonameId={2464470} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      'GET /atlas/places/2464470': { body: PLACE_PAGE },
    });
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'ذاكرة المكان: [تونس]' })
    ).toBeInTheDocument();
  });
});
