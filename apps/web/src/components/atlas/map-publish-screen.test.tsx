import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { OWNER_ENTRY } from '@/test/atlas';
import { USER } from '@/test/fixtures';
import { type FakeSource, forgetMaps, loadedMap } from '@/test/maplibre';
import { IDENTITY, NO_IDENTITY } from '@/test/social';
import { MapPublishScreen } from './map-publish-screen';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
const params = { insight: '7000000000000000001' as string | null };
vi.mock('next/navigation', () => ({
  usePathname: () => '/atlas/publish',
  useSearchParams: () => ({ get: (key: string) => (key === 'insight' ? params.insight : null) }),
}));

afterEach(forgetMaps);

const INSIGHT = '7000000000000000001';

function member(extra: Record<string, Route> = {}, identity: object = IDENTITY) {
  return mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: identity },
    [`GET /insights/${INSIGHT}/map`]: apiError(404, 'NOT_FOUND'),
    ...extra,
  });
}

describe('MapPublishScreen', () => {
  it('asks for an insight first', () => {
    params.insight = null;
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    render(<MapPublishScreen />);
    expect(screen.getByRole('heading', { level: 1, name: 'اختر بصيرة أولًا' })).toBeInTheDocument();
    params.insight = INSIGHT;
  });

  it('sends a guest to sign in and comes back to the same insight', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    render(<MapPublishScreen />);
    expect(await screen.findByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fatlas%2Fpublish%3Finsight%3D7000000000000000001'
    );
  });

  it('asks a member without a public identity to choose one first', async () => {
    member({}, NO_IDENTITY);
    render(<MapPublishScreen />);
    expect(await screen.findByText(/اختر هويتك العامة أولًا/)).toBeInTheDocument();
    expect(screen.getByLabelText('المعرّف')).toBeInTheDocument();
  });

  it('takes the device position, keeps it with the owner, previews the cell and publishes', async () => {
    const api = member({
      [`PUT /insights/${INSIGHT}/map`]: { body: OWNER_ENTRY },
      [`POST /insights/${INSIGHT}/map/publish`]: {
        body: { ...OWNER_ENTRY, status: 'published', published_at: '2026-10-04T09:00:00Z' },
      },
    });
    vi.stubGlobal('navigator', {
      ...navigator,
      geolocation: {
        getCurrentPosition: (ok: (position: unknown) => void) =>
          ok({
            coords: { latitude: 36.806512, longitude: 10.181534, accuracy: 12.4 },
            timestamp: 1_790_000_000_000,
          }),
      },
    });
    render(<MapPublishScreen />);
    expect(await screen.findByText('لم تحدد موضعًا بعد.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'احسب الموضع التقريبي' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'استعمل موضعي الآن' }));
    expect(await screen.findByText(/الموضع المختار: 36.80651, 10.18153/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'احسب الموضع التقريبي' }));
    expect(await screen.findByText(/حُسب موضعك التقريبي/)).toBeInTheDocument();
    expect(await api.bodies('PUT', `/insights/${INSIGHT}/map`)).toEqual([
      {
        latitude: 36.806512,
        longitude: 10.181534,
        accuracy_m: 12,
        source: 'device_capture',
        meaning: 'capture_point',
        measured_at: new Date(1_790_000_000_000).toISOString(),
      },
    ]);
    expect(screen.getByText('[موقع تقريبي ضمن نحو 1000 م]')).toBeInTheDocument();
    expect(screen.getByText('[تونس]، [ولاية تونس]، [تونس البلد]')).toBeInTheDocument();
    const map = await loadedMap();
    expect(
      ((map.getSource('cell') as FakeSource).data as { features: unknown[] }).features
    ).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: 'انشر على الأطلس' }));
    expect(await screen.findByText('نُشرت بصيرتك على الأطلس.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'افتحها على الأطلس' })).toHaveAttribute(
      'href',
      `/atlas/entries/${OWNER_ENTRY.id}`
    );
  });

  it('chooses a place by name as a public place, and says why an insight is refused', async () => {
    const api = member({
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
            country: null,
          },
        ],
      },
      [`PUT /insights/${INSIGHT}/map`]: apiError(409, 'INSIGHT_NOT_PUBLISHABLE'),
    });
    render(<MapPublishScreen />);
    await userEvent.type(await screen.findByLabelText('ابحث عن مكان'), 'mecca');
    await userEvent.click(screen.getByRole('button', { name: 'ابحث عن مدينة أو مكان' }));
    await userEvent.click(await screen.findByRole('button', { name: /\[مكة\]/ }));
    expect(screen.getByRole('radio', { name: 'مكان عام اخترته' })).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: 'احسب الموضع التقريبي' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /لا يمكن وضع هذه البصيرة على الأطلس/
    );
    expect((await api.bodies('PUT', `/insights/${INSIGHT}/map`))[0]).toMatchObject({
      latitude: 21.4225,
      longitude: 39.8262,
      source: 'user_selected',
      meaning: 'public_place',
    });
  });

  it('shows an existing entry, lets the owner withdraw it, and starts over', async () => {
    member({
      [`GET /insights/${INSIGHT}/map`]: {
        body: { ...OWNER_ENTRY, status: 'published', published_at: '2026-10-04T09:00:00Z' },
      },
      [`DELETE /insights/${INSIGHT}/map`]: { status: 204 },
    });
    render(<MapPublishScreen />);
    expect(await screen.findByText('منشورة على الأطلس')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'اسحب من الأطلس' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب' }));
    expect(await screen.findByText(/سُحبت بصيرتك من الأطلس/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'أين التُقطت الصورة؟' })
      ).toBeInTheDocument()
    );
  });

  it('picks a point from a tap on the map', async () => {
    member();
    render(<MapPublishScreen />);
    await screen.findByText('لم تحدد موضعًا بعد.');
    const map = await loadedMap();
    map.emit('click', { point: { x: 1, y: 1 }, lngLat: { lng: 10.2, lat: 36.9 } });
    expect(await screen.findByText(/الموضع المختار: 36.90000, 10.20000/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'احسب الموضع التقريبي' })).toBeEnabled();
  });
});
