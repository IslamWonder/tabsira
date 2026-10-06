import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import type { AtlasFeature } from '@/atlas/types';
import { zoomForRadius } from '@/atlas/view-state';
import { messages } from '@/messages';
import { apiError, mockApi, type Reply, type Route } from '@/test/api';
import { FEATURE, ORPHAN_FEATURE, SECOND_FEATURE } from '@/test/atlas';
import {
  forgetDevice,
  hidePage,
  stubCamera,
  stubGeolocation,
  stubOrientation,
  turnDevice,
} from '@/test/camera';
import { CameraScreen } from './camera-screen';

afterEach(forgetDevice);

// The device stands 850 m from the two sample entries' cell centre, inside their 1000 m cell.
const DEVICE = [10.19, 36.81] as const;
// About 2.5 km due east of the device: outside the first radius, inside the widened one.
const FAR: AtlasFeature = {
  ...FEATURE,
  id: '7400000000000000003',
  geometry: { type: 'Point', coordinates: [10.218, 36.81] },
  properties: { ...FEATURE.properties, id: '7400000000000000003', title: '[بصيرة بعيدة]' },
};

const collection = (features: AtlasFeature[] = [FEATURE, SECOND_FEATURE, FAR]) => ({
  body: { type: 'FeatureCollection', features, truncated: false },
});

function guest(extra: Record<string, Route> = {}) {
  return mockApi({
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    'GET /atlas/entries': collection(),
    ...extra,
  });
}

const windows = (api: ReturnType<typeof mockApi>) =>
  api.requests
    .filter((request) => request.url.includes('/atlas/entries'))
    .map((request) => {
      const query = new URL(request.url).searchParams;
      return [query.get('west'), query.get('south'), query.get('east'), query.get('north')];
    });

async function startExploring(camera: Parameters<typeof stubCamera>[0] = 'granted') {
  const device = stubCamera(camera);
  const geolocation = stubGeolocation();
  const api = guest();
  render(<CameraScreen />);
  await userEvent.click(screen.getByRole('button', { name: 'ابدأ الاستكشاف' }));
  await waitFor(() => expect(geolocation.watchPosition).toHaveBeenCalled());
  return { api, device, geolocation };
}

describe('CameraScreen', () => {
  it('explains what it needs and asks nothing of the device before the tap', () => {
    stubCamera('granted');
    const geolocation = stubGeolocation();
    const api = guest();
    render(<CameraScreen />);
    expect(screen.getByRole('heading', { level: 1, name: 'اكتشف البصائر حولك' })).toBeVisible();
    expect(screen.getByText(/لا تُحفظ منها لقطة ولا تُرسل/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'اعرض على الخريطة' })).toHaveAttribute(
      'href',
      '/atlas'
    );
    expect(navigator.mediaDevices?.getUserMedia).not.toHaveBeenCalled();
    expect(geolocation.watchPosition).not.toHaveBeenCalled();
    expect(api.requests.filter((r) => r.url.includes('/atlas/entries'))).toHaveLength(0);
  });

  it('asks for a widened window around the device, lists what lies inside the radius by distance, and sends no position', async () => {
    const { api, device, geolocation } = await startExploring();
    expect(device.getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'نحدد منطقتك…'
    );
    geolocation.fix(DEVICE);

    const list = await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
    expect(windows(api)).toEqual([['10.15', '36.75', '10.25', '36.85']]);
    const links = within(list).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      `/atlas/entries/${FEATURE.id}`,
      `/atlas/entries/${SECOND_FEATURE.id}`,
    ]);
    expect(within(list).getAllByText('أنت بالقرب من منطقتها')).toHaveLength(2);
    expect(within(list).queryByText('[بصيرة بعيدة]')).toBeNull();
    expect(screen.getByText('بصيرتان')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'العرض بحسب المنطقة'
    );
    // The labels over the view repeat the list for the eye only; no coordinate is written anywhere.
    const overlay = document.querySelectorAll('[aria-hidden="true"] a');
    expect(overlay).toHaveLength(2);
    for (const label of overlay) {
      expect(label).toHaveAttribute('tabindex', '-1');
    }
    expect(document.body.textContent).not.toContain('36.81');
    expect(document.body.textContent).not.toContain('10.19');
    expect(JSON.stringify(api.requests.map((r) => r.url))).not.toContain('10.19');
    // «اعرض على الخريطة» opens the atlas on this view, the nearest entry selected; the centre
    // travels in the fragment, which never reaches a server.
    const toMap = screen.getByRole('link', { name: 'اعرض على الخريطة' }).getAttribute('href');
    expect(toMap).toBe(`/atlas#c=10.19,36.81,${zoomForRadius(1500, 36.81)}&e=${FEATURE.id}`);

    // A small drift asks nothing; a real move asks again, once.
    geolocation.fix([10.1905, 36.8102]);
    expect(windows(api)).toHaveLength(1);
    geolocation.fix([10.2, 36.81]);
    await waitFor(() => expect(windows(api)).toHaveLength(2));

    // Widening the area brings the far entry in with a rounded distance.
    await userEvent.click(screen.getByRole('button', { name: 'وسّع المنطقة' }));
    await waitFor(() => expect(windows(api)).toHaveLength(3));
    expect(await within(list).findByText('[بصيرة بعيدة]')).toBeInTheDocument();
    // After the move every entry lies beyond its cell, so each shows a rounded distance.
    expect(within(list).getAllByText(/نحو (1\.5|2) كم/)).toHaveLength(3);
    expect(document.querySelectorAll('[aria-hidden="true"] a')).toHaveLength(3);
  });

  it('points toward an entry beyond its cell once the sensors give a heading anchored to north', async () => {
    stubOrientation();
    const { geolocation } = await startExploring();
    geolocation.fix(DEVICE);
    await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
    await userEvent.click(screen.getByRole('button', { name: 'وسّع المنطقة' }));
    const list = screen.getByRole('region', { name: 'قائمة البصائر القريبة' });
    await within(list).findByText('[بصيرة بعيدة]');

    await userEvent.click(screen.getByRole('button', { name: 'فعّل الاتجاه' }));
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'ننتظر قراءة الاتجاه…'
    );
    // A relative reading is not a heading.
    turnDevice({ alpha: 270, absolute: false });
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'ننتظر قراءة الاتجاه…'
    );
    // The camera looks east, where the far entry's area lies.
    turnDevice({ alpha: 270 });
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'العرض بالاتجاه التقريبي'
    );
    const far = within(list).getByRole('link', { name: /\[بصيرة بعيدة\]/ });
    expect(within(far).getByText('الاتجاه التقريبي: أمامك')).toBeInTheDocument();
    expect(
      within(far).getByRole('img', { name: 'سهم نحو منطقة البصيرة، أمامك' })
    ).toBeInTheDocument();
    expect(within(far).getByText('في اتجاه الكاميرا')).toBeInTheDocument();
    // Entries inside their own cell get no arrow: a cell centre is not a target.
    const near = within(list).getByRole('link', { name: /^\[عنوان البصيرة\]/ });
    expect(within(near).queryByRole('img')).toBeNull();
    expect(screen.getByText(/لا إلى شيء بعينه/)).toBeInTheDocument();

    // Turning to face north puts the far entry on the right: the heading is smoothed over a few
    // readings and shown at a paced rhythm. A reading straight down is ignored.
    for (let reading = 0; reading < 6; reading += 1) {
      turnDevice({ alpha: 0 });
    }
    turnDevice({ alpha: 0, beta: 0 });
    await waitFor(() =>
      expect(within(far).getByText('الاتجاه التقريبي: عن يمينك')).toBeInTheDocument()
    );
  });

  it('keeps the list when the camera is refused, and lets the reader choose a region when the position is', async () => {
    const { api, geolocation } = await startExploring('denied');
    expect(await screen.findByText(/لم يُمنح إذن الكاميرا/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'أوقف الكاميرا' })).toBeNull();
    geolocation.fail(1);
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'لم يُمنح إذن الموقع'
    );
    expect(screen.queryByRole('button', { name: 'فعّل الاتجاه' })).toBeNull();

    guest({
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
      'GET /atlas/entries': collection([
        { ...FEATURE, geometry: { type: 'Point', coordinates: [39.83, 21.42] } },
      ]),
    });
    await userEvent.type(screen.getByLabelText('ابحث عن مدينة أو مكان'), 'مكة');
    await userEvent.click(screen.getByRole('button', { name: 'ابحث عن مدينة أو مكان' }));
    await userEvent.click(await screen.findByRole('button', { name: /\[مكة\]/ }));
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'استكشاف المنطقة المختارة: [مكة]'
    );
    const list = await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
    expect(await within(list).findByText('[عنوان البصيرة]')).toBeInTheDocument();
    // A chosen region is not the reader's surroundings: no distance, no direction.
    expect(within(list).getByText('في هذه المنطقة')).toBeInTheDocument();
    expect(within(list).queryByText(/نحو /)).toBeNull();
    expect(api.requests).toBeDefined();
  });

  it('says when nothing is published nearby, offers to add or widen, and stops at the widest radius', async () => {
    const { api, geolocation } = await startExploring();
    guest({ 'GET /atlas/entries': collection([]) });
    geolocation.fix(DEVICE, 3_000);
    expect(await screen.findByText(/لا توجد بصائر منشورة قريبة بعد/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'أضف بصيرة' })).toHaveAttribute(
      'href',
      '/atlas/publish'
    );
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      'دقة الموقع منخفضة'
    );
    // The radius starts at twice the fix's error (6 km), doubles twice to the 20 km cap, then stops.
    await userEvent.click(screen.getByRole('button', { name: 'وسّع المنطقة' }));
    await userEvent.click(await screen.findByRole('button', { name: 'وسّع المنطقة' }));
    expect(await screen.findByText('هذا أوسع نطاق نبحث فيه.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'وسّع المنطقة' })).toBeNull();
    expect(api.requests).toBeDefined();
  });

  it('reports a failed request with a retry, and pauses the camera when the page is hidden', async () => {
    const { device, geolocation } = await startExploring();
    guest({ 'GET /atlas/entries': 'network-error' });
    geolocation.fix(DEVICE);
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    guest();
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    const list = screen.getByRole('region', { name: 'قائمة البصائر القريبة' });
    expect(await within(list).findByText('[عنوان البصيرة]')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'أوقف الكاميرا' })).toBeInTheDocument();
    hidePage();
    expect(device.track.stop).toHaveBeenCalled();
    expect(screen.getByText('توقفت الكاميرا حين غادرت الصفحة.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'أعد تشغيل الكاميرا' }));
    expect(device.getUserMedia).toHaveBeenCalledTimes(2);
    await userEvent.click(await screen.findByRole('button', { name: 'أوقف الكاميرا' }));
    expect(screen.queryByRole('button', { name: 'أوقف الكاميرا' })).toBeNull();
    expect(device.track.stop).toHaveBeenCalledTimes(2);
  });

  it('shows the five nearest over the view and the rest on request', async () => {
    const many = Array.from({ length: 7 }, (_, index) => ({
      ...FEATURE,
      id: `740000000000000010${index}`,
      geometry: { type: 'Point' as const, coordinates: [10.19 + index * 0.001, 36.81] },
      properties: {
        ...FEATURE.properties,
        id: `740000000000000010${index}`,
        title: `[بصيرة ${index}]`,
      },
    }));
    stubCamera('none');
    const geolocation = stubGeolocation();
    guest({ 'GET /atlas/entries': collection(many) });
    render(<CameraScreen />);
    await userEvent.click(screen.getByRole('button', { name: 'ابدأ الاستكشاف' }));
    expect(await screen.findByText(/لا تتوفر الكاميرا/)).toBeInTheDocument();
    geolocation.fix(DEVICE);
    const list = await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
    await within(list).findByText('[بصيرة 0]');
    expect(within(list).getAllByRole('link')).toHaveLength(5);
    expect(document.querySelectorAll('[aria-hidden="true"] a')).toHaveLength(5);
    await userEvent.click(screen.getByRole('button', { name: 'اعرض الكل (7)' }));
    expect(within(list).getAllByRole('link')).toHaveLength(7);
    await userEvent.click(screen.getByRole('button', { name: 'اعرض الأقرب فقط' }));
    expect(within(list).getAllByRole('link')).toHaveLength(5);
  });

  it('rounds a distance to metres under a kilometre and to whole kilometres when it is one', async () => {
    // A fine cell 500 m east of the device, and a coarse one about 2 km east.
    const close: AtlasFeature = {
      ...FEATURE,
      id: '7400000000000000004',
      geometry: { type: 'Point', coordinates: [10.19561, 36.81] },
      properties: {
        ...FEATURE.properties,
        id: '7400000000000000004',
        title: '[بصيرة قريبة]',
        cell_m: 100,
        place: null,
      },
    };
    const twoKm: AtlasFeature = {
      ...FEATURE,
      id: '7400000000000000005',
      geometry: { type: 'Point', coordinates: [10.2124, 36.81] },
      properties: { ...FEATURE.properties, id: '7400000000000000005', title: '[بصيرة كيلومترين]' },
    };
    const { geolocation } = await startExploring();
    guest({
      'GET /atlas/entries': {
        body: { type: 'FeatureCollection', features: [close, twoKm], truncated: true },
      },
    });
    geolocation.fix(DEVICE);
    const list = await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
    const near = await within(list).findByRole('link', { name: /\[بصيرة قريبة\]/ });
    expect(within(near).getByText('نحو 500 م')).toBeInTheDocument();
    expect(within(near).getByText('[موقع تقريبي ضمن نحو 1000 م]')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'وسّع المنطقة' }));
    const far = await within(list).findByRole('link', { name: /\[بصيرة كيلومترين\]/ });
    expect(within(far).getByText('نحو 2 كم')).toBeInTheDocument();
    expect(screen.getByText(messages.atlas.truncated)).toBeInTheDocument();
  });

  it('keeps the answer of the last window only when the device moved meanwhile', async () => {
    const waiting: ((reply: Reply) => void)[] = [];
    const { geolocation } = await startExploring();
    const api = guest({
      'GET /atlas/entries': () => new Promise<Reply>((resolve) => waiting.push(resolve)),
    });
    geolocation.fix(DEVICE);
    await waitFor(() => expect(windows(api)).toHaveLength(1));
    geolocation.fix([10.3, 36.81]);
    await waitFor(() => expect(windows(api)).toHaveLength(2));
    waiting[0]?.(collection([FEATURE]));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText('[عنوان البصيرة]')).toBeNull();
    waiting[1]?.(collection([]));
    expect(await screen.findByText(/لا توجد بصائر منشورة قريبة بعد/)).toBeInTheDocument();
  });

  it('says when the device cannot locate itself, and offers a region instead', async () => {
    const { geolocation } = await startExploring();
    geolocation.fail(2);
    expect(screen.getByRole('status', { name: 'حالة الاستكشاف' })).toHaveTextContent(
      messages.atlas.camera.locationUnavailable
    );
    expect(screen.getByLabelText('ابحث عن مدينة أو مكان')).toBeInTheDocument();
  });

  it('gives a direction to an entry that appears while the heading is already known', async () => {
    stubOrientation();
    const { geolocation } = await startExploring();
    geolocation.fix(DEVICE);
    const list = await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
    await userEvent.click(screen.getByRole('button', { name: 'فعّل الاتجاه' }));
    turnDevice({ alpha: 270 });
    await userEvent.click(screen.getByRole('button', { name: 'وسّع المنطقة' }));
    const far = await within(list).findByRole('link', { name: /\[بصيرة بعيدة\]/ });
    expect(within(far).getByText('الاتجاه التقريبي: أمامك')).toBeInTheDocument();
    expect(within(far).getByText('في اتجاه الكاميرا')).toBeInTheDocument();
  });

  describe('with sponsoring', () => {
    const O = messages.atlas.sponsor.orphans;
    const orphans = {
      body: { type: 'FeatureCollection', features: [ORPHAN_FEATURE], next_cursor: null },
    };

    it('offers the orphaned entries around the device, asked with the position snapped to the grid', async () => {
      const device = stubCamera('granted');
      const geolocation = stubGeolocation();
      const api = guest({ 'GET /atlas/orphans': orphans });
      render(<CameraScreen sponsorship />);
      await userEvent.click(screen.getByRole('button', { name: 'ابدأ الاستكشاف' }));
      await waitFor(() => expect(geolocation.watchPosition).toHaveBeenCalled());
      expect(device.getUserMedia).toHaveBeenCalled();
      expect(screen.queryByRole('region', { name: O.heading })).toBeNull();
      geolocation.fix(DEVICE);
      const section = await screen.findByRole('region', { name: O.heading });
      expect(within(section).getByRole('link', { name: /\[بصيرة تنتظر\]/ })).toHaveTextContent(
        '[على مستوى المنطقة]'
      );
      const request = api.requests.find((r) => r.url.includes('/atlas/orphans'));
      const query = new URL(request?.url ?? '').searchParams;
      expect([query.get('lng'), query.get('lat')]).toEqual(['10.2', '36.8']);
      expect(request?.url).not.toContain('10.19');
      expect(request?.url).not.toContain('36.81');
    });

    it('asks nothing about orphans while the feature is off', async () => {
      const { api, geolocation } = await startExploring();
      geolocation.fix(DEVICE);
      await screen.findByRole('region', { name: 'قائمة البصائر القريبة' });
      expect(api.requests.some((r) => r.url.includes('/atlas/orphans'))).toBe(false);
      expect(screen.queryByRole('region', { name: O.heading })).toBeNull();
    });
  });
});
