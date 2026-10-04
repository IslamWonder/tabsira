import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { FEATURE, SECOND_FEATURE } from '@/test/atlas';
import { forgetMaps, loadedMap } from '@/test/maplibre';
import { AtlasScreen } from './atlas-screen';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({ usePathname: () => '/atlas' }));

afterEach(() => {
  forgetMaps();
  window.history.replaceState(null, '', '/atlas');
});

const collection = (features = [FEATURE, SECOND_FEATURE], truncated = false) => ({
  body: { type: 'FeatureCollection', features, truncated },
});

function guest(extra: Record<string, Route> = {}) {
  return mockApi({
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    'GET /atlas/entries': collection(),
    ...extra,
  });
}

describe('AtlasScreen', () => {
  it('asks for the window the map shows and lists what is in it, as the map does', async () => {
    const api = guest();
    render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeInTheDocument();
    const request = api.requests.find((r) => r.url.includes('/atlas/entries'));
    const query = new URL(request?.url ?? '').searchParams;
    expect([query.get('west'), query.get('south'), query.get('east'), query.get('north')]).toEqual([
      '9',
      '35',
      '11',
      '37',
    ]);
    expect(query.get('since')).toBeNull();
    expect(screen.getByText('بصيرتان')).toBeInTheDocument();
    // What the server sent is what is drawn: approximate points, nothing else.
    expect(document.body.textContent).not.toContain('36.8065');
  });

  it('opens an entry from the list, and asks again only when told to after a move', async () => {
    const api = guest();
    render(<AtlasScreen />);
    const map = await loadedMap();
    await userEvent.click(await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ }));
    const cards = screen.getAllByRole('article', { name: /^\[عنوان البصيرة\]/ });
    expect(cards.length).toBeGreaterThan(0);
    expect(
      within(cards[0] as HTMLElement).getByRole('link', { name: 'افتح البصيرة' })
    ).toHaveAttribute('href', `/atlas/entries/${FEATURE.id}`);
    expect(
      within(cards[0] as HTMLElement).getByRole('link', { name: '[اسم عام]' })
    ).toHaveAttribute('href', '/u/rain_reader');
    expect(map.flyTo).toHaveBeenCalled();

    const before = api.requests.filter((r) => r.url.includes('/atlas/entries')).length;
    map.bounds = { west: 39, south: 21, east: 40, north: 22 };
    map.emit('moveend', { originalEvent: {} });
    expect(api.requests.filter((r) => r.url.includes('/atlas/entries')).length).toBe(before);
    await userEvent.click(screen.getByRole('button', { name: 'ابحث في هذه المنطقة' }));
    await waitFor(() =>
      expect(api.requests.filter((r) => r.url.includes('/atlas/entries')).length).toBe(before + 1)
    );
    expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('west')).toBe('39');
  });

  it('says when a window is empty or cut short, and when the API fails', async () => {
    guest({ 'GET /atlas/entries': collection([], false) });
    const { unmount } = render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByText(/لا توجد بصائر منشورة في هذه المنطقة بعد/)).toBeInTheDocument();
    unmount();
    forgetMaps();

    guest({ 'GET /atlas/entries': collection([FEATURE], true) });
    const second = render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByText(/قرّب الخريطة لترى المزيد/)).toBeInTheDocument();
    second.unmount();
    forgetMaps();

    guest({ 'GET /atlas/entries': 'network-error' });
    render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    guest();
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeInTheDocument();
  });

  it('filters by period and country, sending only the window and the filters', async () => {
    const api = guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await userEvent.click(screen.getByRole('radio', { name: 'آخر شهر' }));
    await waitFor(() => {
      const last = new URL(api.requests.at(-1)?.url ?? '').searchParams;
      expect(last.get('since')).not.toBeNull();
    });
    await userEvent.selectOptions(screen.getByLabelText('البلد'), 'SA');
    await waitFor(() =>
      expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('country')).toBe('SA')
    );
    await userEvent.click(screen.getByRole('button', { name: 'امسح المرشحات' }));
    await waitFor(() =>
      expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('country')).toBeNull()
    );
  });

  it('flies to a place found by name, and to the device with its own position, sending neither', async () => {
    const api = guest({
      'GET /geo/search': {
        body: [
          {
            geoname_id: 104515,
            name: 'Mecca',
            name_ar: '[مكة]',
            label: '[مكة]',
            feature_class: 'P',
            feature_code: 'PPLA',
            population: 1,
            latitude: 21.4225,
            longitude: 39.8262,
            location: { type: 'Point', coordinates: [39.8262, 21.4225] },
            admin_area: null,
            country: {
              iso2: 'SA',
              name: 'Saudi Arabia',
              name_ar: '[السعودية]',
              label: '[السعودية]',
            },
          },
        ],
      },
    });
    render(<AtlasScreen />);
    const map = await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await userEvent.type(screen.getByLabelText('ابحث عن مدينة أو مكان'), 'mecca');
    await userEvent.click(screen.getByRole('button', { name: 'ابحث عن مدينة أو مكان' }));
    await userEvent.click(await screen.findByRole('button', { name: /^\[مكة\]/ }));
    expect(map.flyTo).toHaveBeenLastCalledWith(
      expect.objectContaining({ center: [39.8262, 21.4225] })
    );

    const getCurrentPosition = vi.fn((ok: (position: unknown) => void) =>
      ok({ coords: { latitude: 36.0, longitude: 10.0 } })
    );
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } });
    await userEvent.click(screen.getByRole('button', { name: 'قريب مني' }));
    expect(map.flyTo).toHaveBeenLastCalledWith(expect.objectContaining({ center: [10.0, 36.0] }));
    // The position went to the map alone.
    expect(api.requests.some((r) => r.url.includes('36') && r.url.includes('lat'))).toBe(false);

    vi.stubGlobal('navigator', {
      ...navigator,
      geolocation: { getCurrentPosition: (_ok: unknown, fail: () => void) => fail() },
    });
    await userEvent.click(screen.getByRole('button', { name: 'قريب مني' }));
    expect(await screen.findByText(/لم يُمنح إذن الموقع/)).toBeInTheDocument();
  });

  it('opens on the view, selection and filters the address carries, and keeps the address in step', async () => {
    window.history.replaceState(
      null,
      '',
      `/atlas#c=39.826,21.423,11&e=${SECOND_FEATURE.id}&p=month&k=SA`
    );
    const api = guest();
    render(<AtlasScreen />);
    const map = await loadedMap();
    expect(map.options).toMatchObject({ center: [39.826, 21.423], zoom: 11 });
    await screen.findByRole('button', { name: /^\[بصيرة ثانية\]/ });
    const query = new URL(api.requests.at(-1)?.url ?? '').searchParams;
    expect(query.get('since')).not.toBeNull();
    expect(query.get('country')).toBe('SA');
    expect(screen.getByRole('radio', { name: 'آخر شهر' })).toBeChecked();
    expect(screen.getAllByRole('article', { name: '[بصيرة ثانية]' }).length).toBeGreaterThan(0);

    // A hand move, a new selection and a cleared filter are written back, replacing the address.
    map.center = { lng: 10.5, lat: 36.5 };
    map.zoom = 9.25;
    map.emit('moveend', { originalEvent: {} });
    await waitFor(() => expect(window.location.hash).toContain('c=10.5,36.5,9.3'));
    await userEvent.click(screen.getByRole('button', { name: /^\[عنوان البصيرة\]/ }));
    expect(window.location.hash).toContain(`e=${FEATURE.id}`);
    await userEvent.click(screen.getByRole('button', { name: 'امسح المرشحات' }));
    await waitFor(() => expect(window.location.hash).not.toContain('p=month'));
    expect(window.location.hash).toBe(`#c=10.5,36.5,9.3&e=${FEATURE.id}`);
  });

  it('ignores a malformed address and replaces it with what the map shows', async () => {
    window.history.replaceState(null, '', '/atlas#c=nonsense&e=0&p=never');
    guest();
    render(<AtlasScreen />);
    const map = await loadedMap();
    expect(map.options).toMatchObject({ center: [30, 27] });
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(window.location.hash).toBe('#c=10,36,8');
  });
});
