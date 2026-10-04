import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { PLACE_ONE, PLACE_TWO, RELATION, TREASURE, WORLD, WORLD_UNDER_FOG } from '@/test/world';
import { WorldScreen } from './world-screen';

const list = () => screen.getByRole('region', { name: 'المناطق' });
const mapButton = (container: HTMLElement, id: string) =>
  container.querySelector<HTMLButtonElement>(`[data-region="${id}"]`) as HTMLButtonElement;

async function ready(routes: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({ 'GET /world': { body: WORLD }, ...routes });
  const view = render(<WorldScreen />);
  await screen.findByRole('heading', { level: 1, name: 'عالمي' });
  await screen.findByRole('region', { name: 'المناطق' });
  return { api, ...view };
}

describe('WorldScreen states', () => {
  it('says it is opening while the map is on its way', () => {
    mockApi({});
    render(<WorldScreen />);
    expect(screen.getByRole('status')).toHaveTextContent('نفتح خريطة عالمك…');
  });

  it('offers to try again when the map could not be loaded', async () => {
    let calls = 0;
    mockApi({
      'GET /world': () => {
        calls += 1;
        return calls === 1 ? apiError(500, 'internal_error') : { body: WORLD };
      },
    });
    render(<WorldScreen />);
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر فتح عالمك الآن');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByRole('region', { name: 'المناطق' })).toBeInTheDocument();
  });

  it('invites a newcomer to the first scene, with the whole map under fog', async () => {
    mockApi({ 'GET /world': { body: WORLD_UNDER_FOG } });
    render(<WorldScreen />);
    expect(
      await screen.findByRole('heading', { name: 'عالمك ينتظر أول بصيرة' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'ابدأ بأول مشهد' })).toHaveAttribute('href', '/');
    expect(screen.getByText(/انقشع الضباب عن 0 من 4 مناطق/)).toBeInTheDocument();
    expect(screen.getByText('لا خيوط بعد. تظهر حين تصل صلة مسجّلة بين موضعين.')).toBeInTheDocument();
  });
});

describe('the fog map and its list', () => {
  it('draws every region as a button, opened ones glowing and the others under fog', async () => {
    const { container } = await ready();
    expect(container.querySelectorAll('[data-region]')).toHaveLength(4);
    expect(container.querySelectorAll('[data-glow]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-fog]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-thread]')).toHaveLength(1);
    expect(mapButton(container, 'T02')).toHaveAccessibleName('[منطقة ثالثة]، تحت الضباب');
    expect(screen.getByText(/انقشع الضباب عن 2 من 4 مناطق/)).toBeInTheDocument();
  });

  it('keeps the map and the list on one selection', async () => {
    const { container } = await ready();
    await userEvent.click(mapButton(container, 'T02'));
    expect(mapButton(container, 'T02')).toHaveAttribute('aria-pressed', 'true');
    expect(within(list()).getByRole('button', { name: /\[منطقة ثالثة\]/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await userEvent.click(within(list()).getByRole('button', { name: /\[منطقة رابعة\]/ }));
    expect(mapButton(container, 'T02')).toHaveAttribute('aria-pressed', 'false');
    expect(mapButton(container, 'T03')).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('opening a region', () => {
  it('says only a calm line under fog, and records no visit', async () => {
    const { container, api } = await ready();
    await userEvent.click(mapButton(container, 'T02'));
    const heading = screen.getByRole('heading', { level: 2, name: '[منطقة ثالثة]' });
    expect(heading).toHaveFocus();
    expect(screen.getByText(/ينقشع الضباب عن هذه المنطقة حين تتمّ بصيرة/)).toBeInTheDocument();
    expect(api.requests.map((request) => request.method)).toEqual(['GET']);
    await userEvent.click(screen.getByRole('button', { name: 'أغلق التفاصيل' }));
    expect(screen.queryByRole('heading', { level: 2, name: '[منطقة ثالثة]' })).toBeNull();
  });

  it('opens a saved place: its insights lead to their own screen, the visit is recorded', async () => {
    const { container, api } = await ready({
      'POST /world/places/7001/visit': {
        body: { ...PLACE_ONE, last_visited_at: '2026-10-04T08:00:00Z' },
      },
    });
    await userEvent.click(mapButton(container, 'T00'));
    const panel = await screen.findByRole('region', { name: '[منطقة أولى]' });
    expect(within(panel).getByText('[مجال T00]')).toBeInTheDocument();
    expect(within(panel).getByText(/آخر زيارة/)).toBeInTheDocument();
    const link = within(panel).getByRole('link', { name: /\[بصيرة أولى\]/ });
    expect(link).toHaveAttribute('href', '/insight/9001');
    await waitFor(() =>
      expect(api.requests.some((request) => request.method === 'POST')).toBe(true)
    );
  });

  it('shows a place with no visit yet and no insights without a heading for them', async () => {
    const world = {
      ...WORLD,
      places: [{ ...PLACE_ONE, last_visited_at: null, insights: [] }, PLACE_TWO],
    };
    const { container } = await ready({
      'GET /world': { body: world },
      'POST /world/places/7001/visit': { body: world.places[0] },
    });
    await userEvent.click(mapButton(container, 'T00'));
    const panel = await screen.findByRole('region', { name: '[منطقة أولى]' });
    expect(within(panel).queryByText(/آخر زيارة/)).toBeNull();
    expect(within(panel).queryByRole('heading', { name: 'بصائر هذا الموضع' })).toBeNull();
  });

  it('keeps what it showed when the visit could not be recorded', async () => {
    const { container } = await ready({
      'POST /world/places/7001/visit': apiError(500, 'internal_error'),
    });
    await userEvent.click(mapButton(container, 'T00'));
    expect(await screen.findByRole('region', { name: '[منطقة أولى]' })).toBeInTheDocument();
  });

  it('brings a treasure that became ready with the visit', async () => {
    const { container } = await ready({
      'POST /world/places/7001/visit': { body: { ...PLACE_ONE, treasure: { id: '8001' } } },
    });
    expect(screen.queryByRole('button', { name: 'اكشف الكنز' })).toBeNull();
    await userEvent.click(mapButton(container, 'T00'));
    expect(await screen.findByRole('button', { name: 'اكشف الكنز' })).toBeInTheDocument();
  });

  it('reveals a hidden treasure with its verified texts, byte for byte', async () => {
    const { container } = await ready({
      'POST /world/places/7002/visit': { body: PLACE_TWO },
      'POST /world/treasures/8001/reveal': { body: TREASURE },
    });
    await userEvent.click(mapButton(container, 'T01'));
    await userEvent.click(await screen.findByRole('button', { name: 'اكشف الكنز' }));
    const found = await screen.findByRole('heading', { level: 3, name: 'كشفت كنزًا' });
    expect(found).toHaveFocus();
    expect(screen.getByText('[نوع الكنز]')).toBeInTheDocument();
    expect(screen.getByText('[إفصاح الكنز]')).toBeInTheDocument();
  });
});

describe('the threads', () => {
  it('opens a relation whose insights the world does not list without a list of them', async () => {
    mockApi({
      'GET /world': { body: { ...WORLD, relations: [{ ...RELATION, insight_ids: ['9999'] }] } },
    });
    render(<WorldScreen />);
    await userEvent.click(await screen.findByRole('button', { name: '[كيف ترتبطان؟]' }));
    expect(screen.getByText('[سبب الصلة]')).toBeVisible();
    expect(screen.queryByRole('link', { name: /بصيرة/ })).toBeNull();
  });

  it('opens the reason of a recorded relation and draws it stronger', async () => {
    const { container } = await ready();
    const toggle = screen.getByRole('button', { name: '[كيف ترتبطان؟]' });
    expect(screen.getByText('بين «[منطقة أولى]» و«[منطقة ثانية]»')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const line = container.querySelector('[data-thread]') as SVGLineElement;
    const calm = line.getAttribute('stroke-width');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('[سبب الصلة]')).toBeVisible();
    expect(line.getAttribute('stroke-width')).not.toBe(calm);
    // Only the insights the world knows are listed; an unknown id is left out.
    const links = screen.getAllByRole('link', { name: /\[بصيرة (أولى|ثانية)\]/ });
    expect(links.map((link) => link.getAttribute('href'))).toContain('/insight/9002');
    expect(screen.queryByRole('link', { name: /9999/ })).toBeNull();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});
