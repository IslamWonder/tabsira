import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { messages } from '@/messages';
import { apiError, mockApi, type Reply } from '@/test/api';
import { ORPHAN_FEATURE } from '@/test/atlas';
import { OrphansSection } from './orphans-section';

const O = messages.atlas.sponsor.orphans;
const collection = (features = [ORPHAN_FEATURE], next: string | null = null): Reply => ({
  body: { type: 'FeatureCollection', features, next_cursor: next },
});

describe('OrphansSection', () => {
  it('sends the position snapped to the grid and nothing finer, with the default radius', async () => {
    const api = mockApi({ 'GET /atlas/orphans': collection() });
    render(<OrphansSection point={[10.18153, 36.80651]} />);
    await screen.findByRole('region', { name: O.heading });
    const request = api.requests.find((r) => r.url.includes('/atlas/orphans'));
    const query = new URL(request?.url ?? '').searchParams;
    expect(query.get('lng')).toBe('10.2');
    expect(query.get('lat')).toBe('36.8');
    // No coordinate of the exact position is anywhere in the request.
    expect(request?.url).not.toMatch(/10\.18|36\.80[0-9]/);
    for (const value of [query.get('lng'), query.get('lat')]) {
      expect(String(value).split('.')[1]?.length ?? 0).toBeLessThanOrEqual(2);
    }
    expect(query.get('radius')).toBe('150000');
  });

  it('lists each entry at its widened place with its precision label and no author', async () => {
    mockApi({ 'GET /atlas/orphans': collection() });
    render(<OrphansSection point={[10.2, 36.8]} />);
    const list = await screen.findByRole('list', { name: O.list });
    const link = within(list).getByRole('link', { name: /\[بصيرة تنتظر\]/ });
    expect(link).toHaveAttribute('href', `/atlas/entries/${ORPHAN_FEATURE.id}`);
    expect(link).toHaveTextContent('[على مستوى المنطقة]');
    expect(link).toHaveTextContent('[تونس]، [تونس البلد]');
    expect(screen.getByText(O.privacy)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('@');
  });

  it('draws nothing without a point, and nothing when there is nothing to offer', async () => {
    const api = mockApi({ 'GET /atlas/orphans': collection([]) });
    const { container, rerender } = render(<OrphansSection point={null} />);
    expect(container).toBeEmptyDOMElement();
    expect(api.requests).toHaveLength(0);
    rerender(<OrphansSection point={[10.2, 36.8]} />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.requests).toHaveLength(1);
    expect(container).toBeEmptyDOMElement();
  });

  it('asks again only when the grid cell changes, and replaces the list', async () => {
    const api = mockApi({ 'GET /atlas/orphans': collection() });
    const { rerender } = render(<OrphansSection point={[10.2, 36.8]} />);
    await screen.findByRole('list', { name: O.list });
    rerender(<OrphansSection point={[10.21, 36.81]} />);
    expect(api.requests).toHaveLength(1);
    rerender(<OrphansSection point={[11.5, 36.8]} />);
    await screen.findByRole('list', { name: O.list });
    expect(api.requests).toHaveLength(2);
    expect(new URL(api.requests[1]?.url ?? '').searchParams.get('lng')).toBe('11.5');
  });

  it('loads the next page with its cursor and appends it', async () => {
    const second = {
      ...ORPHAN_FEATURE,
      id: '7400000000000000010',
      properties: {
        ...ORPHAN_FEATURE.properties,
        id: '7400000000000000010',
        title: '[بصيرة ثانية تنتظر]',
      },
    };
    const api = mockApi({
      'GET /atlas/orphans': (request) =>
        new URL(request.url).searchParams.get('cursor') === 'c1'
          ? collection([second])
          : collection([ORPHAN_FEATURE], 'c1'),
    });
    render(<OrphansSection point={[10.2, 36.8]} />);
    await userEvent.click(await screen.findByRole('button', { name: O.more }));
    expect(await screen.findByRole('link', { name: /\[بصيرة ثانية تنتظر\]/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /\[بصيرة تنتظر\]/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: O.more })).toBeNull();
    expect(new URL(api.requests[1]?.url ?? '').searchParams.get('cursor')).toBe('c1');
  });

  it('says it quietly when the API fails and tries again on request', async () => {
    mockApi({ 'GET /atlas/orphans': apiError(503, 'SERVICE_UNAVAILABLE') });
    render(<OrphansSection point={[10.2, 36.8]} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(O.failed);
    mockApi({ 'GET /atlas/orphans': collection() });
    await userEvent.click(screen.getByRole('button', { name: messages.atlas.retry }));
    expect(await screen.findByRole('list', { name: O.list })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('forgets an answer that arrives after the position moved on', async () => {
    const waiting: ((reply: Reply) => void)[] = [];
    mockApi({ 'GET /atlas/orphans': () => new Promise<Reply>((resolve) => waiting.push(resolve)) });
    const { rerender } = render(<OrphansSection point={[10.2, 36.8]} />);
    await waitFor(() => expect(waiting).toHaveLength(1));
    rerender(<OrphansSection point={[20.2, 36.8]} />);
    await waitFor(() => expect(waiting).toHaveLength(2));
    waiting[1]?.(collection());
    await screen.findByRole('list', { name: O.list });
    waiting[0]?.(
      collection([
        {
          ...ORPHAN_FEATURE,
          id: '1',
          properties: { ...ORPHAN_FEATURE.properties, id: '1', title: '[قديمة]' },
        },
      ])
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByText('[قديمة]')).toBeNull();
  });
});
