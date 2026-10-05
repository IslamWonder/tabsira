import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setSignedIn } from '@/account/session';
import { messages } from '@/messages';
import { apiError, mockApi, type Reply, type Route } from '@/test/api';
import {
  FEATURE,
  ORPHAN_FEATURE,
  OWNER_ENTRY,
  PLACE,
  SECOND_FEATURE,
  SPONSOR,
  SPONSORSHIP,
} from '@/test/atlas';
import { USER } from '@/test/fixtures';
import { type FakeMap, type FakeSource, forgetMaps, loadedMap } from '@/test/maplibre';

/** A route whose answers the test releases one by one, in the order they were asked. */
function deferred(): {
  route: (request?: Request) => Promise<Reply>;
  answer: (reply: Reply) => void;
} {
  const waiting: ((reply: Reply) => void)[] = [];
  return {
    route: () => new Promise<Reply>((resolve) => waiting.push(resolve)),
    answer: (reply) => waiting.shift()?.(reply),
  };
}

import { AtlasScreen } from './atlas-screen';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({ usePathname: () => '/atlas' }));

afterEach(() => {
  forgetMaps();
  window.history.replaceState(null, '', '/atlas');
});

/** One page of the list beside the map. */
const collection = (
  items = [FEATURE, SECOND_FEATURE],
  total = items.length,
  nextCursor: string | null = null
) => ({ body: { items, next_cursor: nextCursor, total } });

/** What the server drew for the map: every entry alone, as it does from zoom 16. */
const drawn = (features = [FEATURE, SECOND_FEATURE], truncated = false) => ({
  body: {
    type: 'FeatureCollection',
    features: features.map((feature) => ({
      ...feature,
      properties: { ...feature.properties, kind: 'entry' },
    })),
    truncated,
  },
});

const CLUSTER = {
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [10.1, 36.7] },
  properties: { kind: 'cluster', id: 'c-1', count: 12, bbox: [10, 36.6, 10.2, 36.8] },
};

/** What the map was handed to draw. */
const drawnOn = (map: FakeMap) =>
  (
    (map.getSource('entries') as FakeSource).data as {
      features: { properties: { id: string; kind: string; count?: number } }[];
    }
  ).features;

const PAGE = '/atlas/entries/page';
const CLUSTERS = '/atlas/clusters';
const asked = (api: { requests: Request[] }, path: string) =>
  api.requests.filter((r) => new URL(r.url).pathname === path);
const queryOf = (request: Request | undefined) => new URL(request?.url ?? '').searchParams;

function guest(extra: Record<string, Route> = {}) {
  return mockApi({
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    [`GET ${CLUSTERS}`]: drawn(),
    [`GET ${PAGE}`]: collection(),
    ...extra,
  });
}

describe('AtlasScreen', () => {
  it('asks for the window the map shows and lists what is in it, as the map does', async () => {
    const api = guest();
    render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeInTheDocument();
    // The list asks for the window the map shows, around its centre; the map for the window padded by a quarter.
    const query = queryOf(asked(api, PAGE)[0]);
    expect([query.get('west'), query.get('south'), query.get('east'), query.get('north')]).toEqual([
      '9',
      '35',
      '11',
      '37',
    ]);
    expect([query.get('center_lng'), query.get('center_lat'), query.get('limit')]).toEqual([
      '10',
      '36',
      '20',
    ]);
    expect(query.get('since')).toBeNull();
    const wide = queryOf(asked(api, CLUSTERS)[0]);
    expect([wide.get('west'), wide.get('south'), wide.get('east'), wide.get('north')]).toEqual([
      '8.5',
      '34.5',
      '11.5',
      '37.5',
    ]);
    expect(wide.get('zoom')).toBe('8');
    expect(screen.getByText('بصيرتان')).toBeInTheDocument();
    // What the server sent is what is drawn: approximate points, nothing else.
    expect(document.body.textContent).not.toContain('36.8065');
  });

  it('opens an entry from the list, and asks again for the new window once the map has moved', async () => {
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

    const before = asked(api, PAGE).length;
    map.bounds = { west: 39, south: 21, east: 40, north: 22 };
    map.emit('moveend', { originalEvent: {} });
    // Not at once: the map has to stand still for a moment first.
    expect(asked(api, PAGE)).toHaveLength(before);
    await waitFor(() => expect(asked(api, PAGE)).toHaveLength(before + 1));
    expect(queryOf(asked(api, PAGE).at(-1)).get('west')).toBe('39');
    expect(screen.queryByRole('button', { name: 'ابحث في هذه المنطقة' })).toBeNull();
  });

  it('names no author beside an entry whose place was widened', async () => {
    const widened = { ...FEATURE, properties: { ...FEATURE.properties, author: null } };
    guest({ [`GET ${PAGE}`]: collection([widened]) });
    render(<AtlasScreen />);
    await loadedMap();
    await userEvent.click(await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ }));
    const card = screen.getAllByRole('article', { name: /^\[عنوان البصيرة\]/ })[0] as HTMLElement;
    expect(within(card).queryByRole('link', { name: '[اسم عام]' })).toBeNull();
    expect(within(card).getByRole('link', { name: 'افتح البصيرة' })).toBeInTheDocument();
  });

  it('says when a window is empty or cut short, and when the API fails', async () => {
    guest({ [`GET ${PAGE}`]: collection([]) });
    const { unmount } = render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByText(/لا توجد بصائر منشورة في هذه المنطقة بعد/)).toBeInTheDocument();
    unmount();
    forgetMaps();

    guest({ [`GET ${CLUSTERS}`]: drawn([FEATURE], true) });
    const second = render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByText(/قرّب الخريطة لترى المزيد/)).toBeInTheDocument();
    second.unmount();
    forgetMaps();

    guest({ [`GET ${PAGE}`]: 'network-error' });
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
      ok({ coords: { latitude: 36.123, longitude: 10.456 } })
    );
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } });
    await userEvent.click(screen.getByRole('button', { name: 'قريب مني' }));
    expect(map.flyTo).toHaveBeenLastCalledWith(
      expect.objectContaining({ center: [10.456, 36.123] })
    );
    // The position went to the map alone.
    expect(api.requests.some((r) => r.url.includes('36.123') || r.url.includes('10.456'))).toBe(
      false
    );

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

  it('filters by a concept the address names, says so, and lets the reader clear it', async () => {
    window.history.replaceState(null, '', '/atlas#t=E012');
    const api = guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('concept')).toBe('E012');
    expect(screen.getByText(/بالمعنى نفسه/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'امسح المعنى' }));
    await waitFor(() =>
      expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('concept')).toBeNull()
    );
    expect(screen.queryByText(/بالمعنى نفسه/)).toBeNull();
    expect(window.location.hash).not.toContain('t=');
  });

  it("lists the signed-in owner's own entries on request, in every state, and shows a public one on the map", async () => {
    setSignedIn(USER);
    const published = {
      ...OWNER_ENTRY,
      id: '7400000000000000002',
      insight_id: '7000000000000000002',
      title: '[بصيرتي المنشورة]',
      status: 'published' as const,
      published_at: '2026-10-04T09:00:00Z',
    };
    const withdrawn = {
      ...OWNER_ENTRY,
      id: '7400000000000000003',
      insight_id: '7000000000000000003',
      title: '[بصيرتي المسحوبة]',
      status: 'withdrawn' as const,
      capture: null,
      public: null,
      place: null,
    };
    const api = guest({ 'GET /me/map-entries': { body: [OWNER_ENTRY, published, withdrawn] } });
    render(<AtlasScreen />);
    const map = await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(api.requests.some((r) => r.url.includes('/me/map-entries'))).toBe(false);

    await userEvent.click(screen.getByRole('radio', { name: 'بصائري المنشورة' }));
    const mine = await screen.findByRole('region', { name: 'بصائري على الأطلس' });
    expect(await within(mine).findByText('[بصيرتي المنشورة]')).toBeInTheDocument();
    expect(within(mine).getByText('موضع محفوظ، لم يُنشر، [تونس]')).toBeInTheDocument();
    expect(within(mine).getByText('منشورة على الأطلس، [تونس]')).toBeInTheDocument();
    expect(within(mine).getByText('مسحوبة')).toBeInTheDocument();
    expect(within(mine).getAllByRole('link', { name: 'افتحها على الأطلس' })).toHaveLength(1);
    expect(within(mine).getByRole('link', { name: 'افتحها على الأطلس' })).toHaveAttribute(
      'href',
      '/atlas/entries/7400000000000000002'
    );
    expect(
      within(mine)
        .getAllByRole('link', { name: 'راجع الموضع' })
        .map((link) => link.getAttribute('href'))
    ).toEqual([
      '/atlas/publish?insight=7000000000000000001',
      '/atlas/publish?insight=7000000000000000002',
      '/atlas/publish?insight=7000000000000000003',
    ]);
    // The private capture point is never written; the public cell centre moves the map.
    expect(document.body.textContent).not.toContain('36.806512');
    expect(within(mine).getAllByRole('button', { name: 'اعرض على الخريطة' })).toHaveLength(2);
    await userEvent.click(
      within(mine).getAllByRole('button', { name: 'اعرض على الخريطة' })[0] as HTMLElement
    );
    expect(map.flyTo).toHaveBeenLastCalledWith(
      expect.objectContaining({ center: [10.1815, 36.8065], zoom: 12 })
    );
    expect(screen.getByRole('region', { name: 'قائمة البصائر في المنطقة' })).toHaveClass('hidden');

    await userEvent.click(screen.getByRole('radio', { name: 'بصائر الناس' }));
    expect(screen.queryByRole('region', { name: 'بصائري على الأطلس' })).toBeNull();
    expect(screen.getByRole('region', { name: 'قائمة البصائر في المنطقة' })).not.toHaveClass(
      'hidden'
    );
  });

  it("offers a guest no entries of their own, and says when the owner's cannot be read", async () => {
    guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(screen.queryByRole('radio', { name: 'بصائري المنشورة' })).toBeNull();

    setSignedIn(USER);
    guest({ 'GET /me/map-entries': 'network-error' });
    await userEvent.click(await screen.findByRole('radio', { name: 'بصائري المنشورة' }));
    const mine = await screen.findByRole('region', { name: 'بصائري على الأطلس' });
    expect(await within(mine).findByRole('alert')).toBeInTheDocument();
    guest({ 'GET /me/map-entries': { body: [] } });
    await userEvent.click(within(mine).getByRole('button', { name: 'أعد المحاولة' }));
    expect(await within(mine).findByText(/لم تضع بصيرة على الأطلس بعد/)).toBeInTheDocument();
  });

  it('shows an entry without a place by its precision, closes its card from the panel and from the sheet', async () => {
    const noPlace = {
      ...FEATURE,
      id: '7400000000000000009',
      properties: { ...FEATURE.properties, id: '7400000000000000009', place: null },
    };
    guest({ [`GET ${PAGE}`]: collection([noPlace]) });
    render(<AtlasScreen />);
    await loadedMap();
    const item = await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(item).toHaveTextContent('[موقع تقريبي ضمن نحو 1000 م]');
    await userEvent.click(item);
    const cards = screen.getAllByRole('article', { name: '[عنوان البصيرة]' });
    expect(cards).toHaveLength(2);
    for (const card of cards) {
      expect(within(card).queryByRole('link', { name: /\[تونس\]/ })).toBeNull();
    }
    const panelCard = cards.find((card) => within(card).queryByRole('button', { name: 'أغلق' }));
    await userEvent.click(within(panelCard as HTMLElement).getByRole('button', { name: 'أغلق' }));
    expect(screen.queryByRole('article')).toBeNull();
    await userEvent.click(item);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('article')).toBeNull();
  });

  it('searches a place only from two characters, says when nothing or no answer came, and drops a late answer', async () => {
    const search = deferred();
    const api = guest({ 'GET /geo/search': search.route });
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    const field = screen.getByLabelText('ابحث عن مدينة أو مكان');
    const form = screen.getByRole('form', { name: messages.atlas.searchForm });
    await userEvent.type(field, 'm');
    fireEvent.submit(form);
    expect(api.requests.some((r) => r.url.includes('/geo/search'))).toBe(false);

    await userEvent.type(field, 'ecca');
    fireEvent.submit(form);
    await waitFor(() =>
      expect(api.requests.filter((r) => r.url.includes('/geo/search'))).toHaveLength(1)
    );
    fireEvent.submit(form);
    await waitFor(() =>
      expect(api.requests.filter((r) => r.url.includes('/geo/search'))).toHaveLength(2)
    );
    // The first answer arrives after the second question: it is not shown.
    search.answer(apiError(500, 'INTERNAL'));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('alert')).toBeNull();
    search.answer({ body: [] });
    expect(await screen.findByRole('status')).toHaveTextContent(messages.atlas.noPlaces);

    guest({ 'GET /geo/search': apiError(500, 'INTERNAL') });
    fireEvent.submit(form);
    expect(await screen.findByRole('alert')).toHaveTextContent(messages.errors.server);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('names a country by its code when it has no label, and lets the reader choose any country again', async () => {
    const unlabelled = {
      ...SECOND_FEATURE,
      properties: {
        ...SECOND_FEATURE.properties,
        place: { ...PLACE, geoname_id: 104515, country_iso2: 'SA', country_label: null },
      },
    };
    const api = guest({
      [`GET ${PAGE}`]: collection([FEATURE, unlabelled]),
      [`GET ${CLUSTERS}`]: drawn([FEATURE, unlabelled]),
    });
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[بصيرة ثانية\]/ });
    expect(screen.getByRole('option', { name: 'SA' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('البلد'), 'SA');
    await waitFor(() =>
      expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('country')).toBe('SA')
    );
    await userEvent.selectOptions(screen.getByLabelText('البلد'), '');
    await waitFor(() =>
      expect(new URL(api.requests.at(-1)?.url ?? '').searchParams.get('country')).toBeNull()
    );
    expect(screen.queryByRole('button', { name: 'امسح المرشحات' })).toBeNull();
  });

  it('keeps the answer of the last question only, and asks nothing before the map has a window', async () => {
    const entries = deferred();
    const api = guest({ [`GET ${PAGE}`]: entries.route });
    render(<AtlasScreen />);
    expect(asked(api, PAGE)).toHaveLength(0);
    await loadedMap();
    await waitFor(() => expect(asked(api, PAGE)).toHaveLength(1));
    await userEvent.click(screen.getByRole('radio', { name: 'آخر شهر' }));
    await waitFor(() => expect(asked(api, PAGE)).toHaveLength(2));
    // The first question was cancelled by the second: its late answer is not shown.
    expect(asked(api, PAGE)[0]?.signal.aborted).toBe(true);
    entries.answer(collection([FEATURE, SECOND_FEATURE]));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeNull();
    entries.answer(collection([SECOND_FEATURE]));
    expect(await screen.findByRole('button', { name: /^\[بصيرة ثانية\]/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeNull();
  });

  it('says when the device cannot locate itself at all', async () => {
    guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    vi.stubGlobal('navigator', { ...navigator, geolocation: undefined });
    await userEvent.click(screen.getByRole('button', { name: 'قريب مني' }));
    expect(screen.getByRole('status')).toHaveTextContent(messages.atlas.nearMeUnavailable);
  });

  it("forgets the owner's entries when they arrive after the list was closed", async () => {
    setSignedIn(USER);
    const mine = deferred();
    guest({ 'GET /me/map-entries': mine.route });
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await userEvent.click(screen.getByRole('radio', { name: 'بصائري المنشورة' }));
    expect(await screen.findByRole('region', { name: 'بصائري على الأطلس' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'بصائر الناس' }));
    mine.answer({ body: [OWNER_ENTRY] });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('region', { name: 'بصائري على الأطلس' })).toBeNull();
    expect(screen.queryByText('[عنوان البصيرة]', { selector: 'h3' })).toBeNull();
  });
});

describe('AtlasScreen with groups and pages', () => {
  const more = messages.atlas.loadMore;
  const second = { ...SECOND_FEATURE };

  it('hands the map what the server grouped, and tells the list apart from it', async () => {
    const entries = drawn([FEATURE]).body;
    guest({
      [`GET ${CLUSTERS}`]: { body: { ...entries, features: [CLUSTER, ...entries.features] } },
    });
    render(<AtlasScreen />);
    const map = await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await waitFor(() => expect(drawnOn(map)).toHaveLength(2));
    const data = drawnOn(map);
    expect(data.map((feature) => feature.properties.kind)).toEqual(['cluster', 'entry']);
    expect(data[0]?.properties.count).toBe(12);
  });

  it('says the true total, loads the next page on request, appends it and drops a repeat', async () => {
    const api = guest({
      [`GET ${PAGE}`]: (request) =>
        queryOf(request).get('cursor') === null
          ? collection([FEATURE], 45, 'next-1')
          : collection([FEATURE, second], 45, null),
    });
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(screen.getByRole('heading', { name: /45 بصيرة/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: more }));
    expect(await screen.findByRole('button', { name: /^\[بصيرة ثانية\]/ })).toBeInTheDocument();
    // The same window and centre, with the cursor; a repeated entry is not listed twice.
    const [first, next] = asked(api, PAGE).map(queryOf);
    expect(next?.get('cursor')).toBe('next-1');
    for (const key of ['west', 'south', 'east', 'north', 'center_lat', 'center_lng']) {
      expect(next?.get(key)).toBe(first?.get(key));
    }
    expect(screen.getAllByRole('button', { name: /^\[عنوان البصيرة\]/ })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: more })).toBeNull();
  });

  it('says so when a page cannot be loaded, keeps what is listed, and tries again on request', async () => {
    let fail = true;
    guest({
      [`GET ${PAGE}`]: (request) =>
        queryOf(request).get('cursor') === null
          ? collection([FEATURE], 2, 'next-1')
          : fail
            ? apiError(500, 'INTERNAL')
            : collection([second], 2, null),
    });
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await userEvent.click(screen.getByRole('button', { name: more }));
    expect(await screen.findByRole('alert')).toHaveTextContent(messages.atlas.loadMoreFailed);
    expect(screen.getByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole('button', { name: more }));
    expect(await screen.findByRole('button', { name: /^\[بصيرة ثانية\]/ })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('goes back to the first page when the window moves, and drops a page that arrives late', async () => {
    const late = deferred();
    let held = false;
    const api = guest({
      [`GET ${PAGE}`]: (request) => {
        if (queryOf(request).get('cursor') !== null) {
          held = true;
          return late.route(request);
        }
        return collection([FEATURE], 45, 'next-1');
      },
    });
    render(<AtlasScreen />);
    const map = await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await userEvent.click(screen.getByRole('button', { name: more }));
    await waitFor(() => expect(held).toBe(true));
    expect(screen.getByRole('button', { name: messages.atlas.loadingMore })).toBeDisabled();
    map.bounds = { west: 39, south: 21, east: 40, north: 22 };
    map.center = { lng: 39.5, lat: 21.5 };
    map.emit('moveend', { originalEvent: {} });
    await waitFor(() => expect(asked(api, PAGE)).toHaveLength(3));
    expect(queryOf(asked(api, PAGE)[2]).get('cursor')).toBeNull();
    late.answer(collection([second], 45, null));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('button', { name: /^\[بصيرة ثانية\]/ })).toBeNull();
    expect(await screen.findByRole('button', { name: more })).toBeEnabled();
  });

  it('waits for the map to stand still, and skips a view that did not change', async () => {
    const api = guest();
    render(<AtlasScreen />);
    const map = await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    vi.useFakeTimers();
    try {
      const still = () => {
        map.emit('moveend', { originalEvent: {} });
        return vi.advanceTimersByTimeAsync(250);
      };
      // The same view again, and a centre nudged inside the same grid cell: nothing is asked.
      await still();
      map.center = { lng: 10.01, lat: 36.01 };
      await still();
      expect(asked(api, CLUSTERS)).toHaveLength(1);
      expect(asked(api, PAGE)).toHaveLength(1);

      // Two moves inside the quiet time make one question, for the last window.
      map.bounds = { west: 20, south: 30, east: 22, north: 32 };
      map.center = { lng: 21, lat: 31 };
      map.emit('moveend', { originalEvent: {} });
      await vi.advanceTimersByTimeAsync(200);
      expect(asked(api, CLUSTERS)).toHaveLength(1);
      map.bounds = { west: 39, south: 21, east: 41, north: 23 };
      map.center = { lng: 40, lat: 22 };
      await still();
      expect(asked(api, CLUSTERS)).toHaveLength(2);
      expect(asked(api, PAGE)).toHaveLength(2);
      expect(queryOf(asked(api, PAGE)[1]).get('west')).toBe('39');

      // A zoom that rounds to the same level is not asked again; a new level is, for the map only.
      map.zoom = 8.3;
      await still();
      expect(asked(api, CLUSTERS)).toHaveLength(2);
      map.zoom = 9;
      await still();
      expect(asked(api, CLUSTERS)).toHaveLength(3);
      expect(asked(api, PAGE)).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('cancels a map question a newer one outdates', async () => {
    const drawing = deferred();
    const api = guest({ [`GET ${CLUSTERS}`]: drawing.route });
    render(<AtlasScreen />);
    const map = await loadedMap();
    await waitFor(() => expect(asked(api, CLUSTERS)).toHaveLength(1));
    map.bounds = { west: 39, south: 21, east: 41, north: 23 };
    map.center = { lng: 40, lat: 22 };
    map.emit('moveend', { originalEvent: {} });
    await waitFor(() => expect(asked(api, CLUSTERS)).toHaveLength(2));
    expect(asked(api, CLUSTERS)[0]?.signal.aborted).toBe(true);
    drawing.answer(drawn([FEATURE]));
    drawing.answer(drawn([SECOND_FEATURE]));
    await waitFor(() => expect(drawnOn(map)[0]?.properties.id).toBe(SECOND_FEATURE.id));
  });

  it('asks again for the same view when the filters change, even though the window did not', async () => {
    const api = guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    await userEvent.click(screen.getByRole('radio', { name: 'آخر أسبوع' }));
    await waitFor(() => expect(asked(api, CLUSTERS)).toHaveLength(2));
    await waitFor(() => expect(asked(api, PAGE)).toHaveLength(2));
    expect(queryOf(asked(api, PAGE)[1]).get('since')).not.toBeNull();
  });

  it('keeps the card of an entry picked on the map after a move that no longer lists it', async () => {
    guest();
    render(<AtlasScreen />);
    const map = await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    map.emit('click:points', { features: [{ properties: { id: FEATURE.id } }] });
    expect(await screen.findAllByRole('article', { name: '[عنوان البصيرة]' })).not.toHaveLength(0);
    guest({
      [`GET ${CLUSTERS}`]: drawn([], false),
      [`GET ${PAGE}`]: collection([], 0),
    });
    map.bounds = { west: 39, south: 21, east: 41, north: 23 };
    map.center = { lng: 40, lat: 22 };
    map.emit('moveend', { originalEvent: {} });
    expect(await screen.findByText(/لا توجد بصائر منشورة في هذه المنطقة بعد/)).toBeInTheDocument();
    expect(screen.getAllByRole('article', { name: '[عنوان البصيرة]' }).length).toBeGreaterThan(0);
  });

  it('shows no card for a selected id nobody has loaded yet', async () => {
    window.history.replaceState(null, '', '/atlas#e=7400000000000000777');
    guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(screen.queryByRole('article')).toBeNull();
  });

  it('says when the groups cannot be loaded, and asks both again on request', async () => {
    guest({ [`GET ${CLUSTERS}`]: 'network-error' });
    render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    // The list is not held back by the map.
    expect(await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ })).toBeInTheDocument();
    guest();
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it('says to zoom in when the server cut the groups short', async () => {
    guest({ [`GET ${CLUSTERS}`]: drawn([FEATURE], true) });
    render(<AtlasScreen />);
    await loadedMap();
    expect(await screen.findByText(messages.atlas.truncated)).toBeInTheDocument();
  });
});

describe('AtlasScreen with sponsoring', () => {
  const S = messages.atlas.sponsor;
  const orphans = (features = [ORPHAN_FEATURE]) => ({
    body: { type: 'FeatureCollection', features, next_cursor: null },
  });

  it('offers nothing of it while the feature is off', async () => {
    setSignedIn(USER);
    const api = guest();
    render(<AtlasScreen />);
    await loadedMap();
    await screen.findByRole('button', { name: /^\[عنوان البصيرة\]/ });
    expect(api.requests.some((r) => r.url.includes('/atlas/orphans'))).toBe(false);
    expect(screen.queryByRole('region', { name: S.orphans.heading })).toBeNull();
    expect(screen.queryByRole('radio', { name: S.list.heading })).toBeNull();
  });

  it('suggests the orphaned entries around the map centre, snapped to the grid, without asking the device', async () => {
    const geolocation = { getCurrentPosition: vi.fn(), watchPosition: vi.fn() };
    vi.stubGlobal('navigator', { ...navigator, geolocation });
    const api = guest({ 'GET /atlas/orphans': orphans() });
    render(<AtlasScreen sponsorship />);
    await loadedMap();
    const section = await screen.findByRole('region', { name: S.orphans.heading });
    const link = within(section).getByRole('link', { name: /\[بصيرة تنتظر\]/ });
    expect(link).toHaveTextContent('[على مستوى المنطقة]');
    expect(link.textContent).not.toContain('@');
    const request = api.requests.find((r) => r.url.includes('/atlas/orphans'));
    const query = new URL(request?.url ?? '').searchParams;
    expect([query.get('lng'), query.get('lat')]).toEqual(['10', '36']);
    expect(geolocation.getCurrentPosition).not.toHaveBeenCalled();
    expect(geolocation.watchPosition).not.toHaveBeenCalled();
  });

  it('asks again around the new centre once the map has moved', async () => {
    const api = guest({ 'GET /atlas/orphans': orphans() });
    render(<AtlasScreen sponsorship />);
    const map = await loadedMap();
    await screen.findByRole('region', { name: S.orphans.heading });
    map.bounds = { west: 39, south: 21, east: 40, north: 22 };
    map.center = { lng: 39.52, lat: 21.48 };
    map.emit('moveend', { originalEvent: {} });
    const orphansAsked = () => asked(api, '/atlas/orphans');
    expect(orphansAsked()).toHaveLength(1);
    await waitFor(() => expect(orphansAsked()).toHaveLength(2));
    const query = new URL(orphansAsked()[1]?.url ?? '').searchParams;
    expect([query.get('lng'), query.get('lat')]).toEqual(['39.5', '21.5']);
  });

  it('opens «كفالاتي» from the scopes of a signed-in member, in place of the lists', async () => {
    setSignedIn(USER);
    guest({
      'GET /atlas/orphans': orphans(),
      'GET /me/sponsorships': { body: [SPONSORSHIP] },
    });
    render(<AtlasScreen sponsorship />);
    await loadedMap();
    await screen.findByRole('region', { name: S.orphans.heading });
    await userEvent.click(await screen.findByRole('radio', { name: S.list.heading }));
    const mine = await screen.findByRole('region', { name: S.list.heading });
    expect(await within(mine).findByText('[بصيرة تنتظر]')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'قائمة البصائر في المنطقة' })).toHaveClass('hidden');
    expect(screen.queryByRole('region', { name: S.orphans.heading })).toBeNull();
    await userEvent.click(screen.getByRole('radio', { name: 'بصائر الناس' }));
    expect(screen.queryByRole('region', { name: S.list.heading })).toBeNull();
    expect(await screen.findByRole('region', { name: S.orphans.heading })).toBeInTheDocument();
  });

  it("shows an orphaned entry of the member's own with its label, and a sponsored one with its sponsor", async () => {
    setSignedIn(USER);
    const orphaned = {
      ...OWNER_ENTRY,
      id: '7400000000000000004',
      insight_id: '7000000000000000004',
      title: '[بصيرتي اليتيمة]',
      status: 'orphaned' as const,
      public: { ...(OWNER_ENTRY.public as NonNullable<typeof OWNER_ENTRY.public>), cell: null },
    };
    const sponsored = {
      ...orphaned,
      id: '7400000000000000005',
      insight_id: '7000000000000000005',
      title: '[بصيرتي المكفولة]',
      status: 'published' as const,
      sponsor: SPONSOR,
    };
    guest({
      'GET /atlas/orphans': orphans([]),
      'GET /me/map-entries': { body: [orphaned, sponsored] },
    });
    render(<AtlasScreen sponsorship />);
    await loadedMap();
    await userEvent.click(await screen.findByRole('radio', { name: 'بصائري المنشورة' }));
    const mine = await screen.findByRole('region', { name: 'بصائري على الأطلس' });
    expect(await within(mine).findByText('[بصيرتي اليتيمة]')).toBeInTheDocument();
    expect(within(mine).getByText(`${S.mine.orphaned}`)).toBeInTheDocument();
    expect(within(mine).getByText('بصيرة تنتظر من يكفلها، [تونس]')).toBeInTheDocument();
    expect(within(mine).getByText(S.mine.by('[اسم الكافل] @quiet_keeper'))).toBeInTheDocument();
    expect(within(mine).getAllByRole('link', { name: 'افتحها على الأطلس' })).toHaveLength(2);
  });

  it('names the sponsor of an own entry by the handle when there is no public name', async () => {
    setSignedIn(USER);
    guest({
      'GET /atlas/orphans': orphans([]),
      'GET /me/map-entries': {
        body: [
          {
            ...OWNER_ENTRY,
            status: 'published' as const,
            sponsor: { ...SPONSOR, public_name: null },
          },
        ],
      },
    });
    render(<AtlasScreen sponsorship />);
    await loadedMap();
    await userEvent.click(await screen.findByRole('radio', { name: 'بصائري المنشورة' }));
    const mine = await screen.findByRole('region', { name: 'بصائري على الأطلس' });
    expect(await within(mine).findByText(S.mine.by('@quiet_keeper'))).toBeInTheDocument();
  });

  it('tells the author, on their own entry, that its place was widened for anonymity', async () => {
    setSignedIn(USER);
    const widened = {
      ...OWNER_ENTRY,
      title: '[بصيرتي الموسعة]',
      status: 'published' as const,
      widened: { level: 'region' as const, label: '[ولاية تونس]', at: '2026-10-05T04:10:00Z' },
    };
    const unnamed = {
      ...widened,
      id: '7400000000000000006',
      insight_id: '7000000000000000006',
      title: '[بلا اسم]',
      widened: { level: 'country' as const, label: null, at: '2026-10-05T04:10:00Z' },
    };
    guest({
      'GET /atlas/orphans': orphans([]),
      'GET /me/map-entries': { body: [widened, unnamed] },
    });
    render(<AtlasScreen />);
    await loadedMap();
    await userEvent.click(await screen.findByRole('radio', { name: 'بصائري المنشورة' }));
    const mine = await screen.findByRole('region', { name: 'بصائري على الأطلس' });
    expect(
      await within(mine).findByText(/اتسع موضعها العام إلى \[ولاية تونس\]/)
    ).toBeInTheDocument();
    expect(within(mine).getByText(/اتسع موضعها العام إلى دولتها/)).toBeInTheDocument();
  });
});
