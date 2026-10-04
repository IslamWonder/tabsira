import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { insightOut, scanOut } from '@/test/scan';
import InsightPage, { metadata as insightMetadata } from './insight/[id]/page';
import ScanPage, { metadata as scanMetadata } from './scan/[id]/page';

class NotFoundSignal extends Error {}

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn() }),
  notFound: () => {
    throw new NotFoundSignal('not found');
  },
}));

const ID = '110000000000000001';
const params = (id: string) => ({ params: Promise.resolve({ id }) });

describe('the pages of the journey', () => {
  it('open an insight and a scan by their public id, and are never indexed', async () => {
    mockApi({
      [`GET /insights/${ID}`]: { body: insightOut() },
      [`GET /scans/${ID}`]: { body: scanOut() },
    });
    render(await InsightPage(params(ID)));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'عنوان البصيرة الأولى' })
    ).toBeInTheDocument();
    expect(insightMetadata.robots).toEqual({ index: false, follow: false });
    expect(insightMetadata.title).toBe('بصيرتك');
    expect(scanMetadata.robots).toEqual({ index: false, follow: false });
    expect(scanMetadata.title).toBe('مشهدك');
  });

  it('open a scan the same way', async () => {
    mockApi({ [`GET /scans/${ID}`]: { body: scanOut() } });
    render(await ScanPage(params(ID)));
    expect(await screen.findByRole('heading', { level: 1, name: 'مشهدك' })).toBeInTheDocument();
  });

  it('answer not found for anything that is not a public id, without asking the API', async () => {
    const api = mockApi({});
    await expect(InsightPage(params('abc'))).rejects.toBeInstanceOf(NotFoundSignal);
    await expect(ScanPage(params('0'))).rejects.toBeInstanceOf(NotFoundSignal);
    expect(api.requests).toHaveLength(0);
  });
});
