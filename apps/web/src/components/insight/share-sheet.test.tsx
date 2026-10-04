import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { ShareSheet, type ShareSheetProps } from './share-sheet';

const ID = '110000000000000002';
const PATH = `/insights/${ID}`;
const URL_OF_PAGE = `https://tabsira.test${PATH}`;
const PUBLISHED = {
  insight_id: ID,
  published: true,
  published_at: '2026-10-04T09:00:00Z',
  path: PATH,
};
const WITHDRAWN = { insight_id: ID, published: false, published_at: null, path: null };

function renderSheet(props: Partial<ShareSheetProps> = {}) {
  render(
    <ShareSheet
      open
      onClose={vi.fn()}
      insightId={ID}
      insightTitle="[العنوان]"
      published={false}
      {...props}
    />
  );
  return screen.getByRole('dialog', { name: 'شارك البصيرة' });
}

function stubShare(share: unknown, clipboard?: unknown) {
  vi.stubGlobal('navigator', { ...navigator, share, clipboard });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ShareSheet', () => {
  it('is not there until it is opened', () => {
    render(
      <ShareSheet
        open={false}
        onClose={vi.fn()}
        insightId={ID}
        insightTitle="[العنوان]"
        published={false}
      />
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('says in one paragraph what becomes public before the first publication, with no withdraw yet', () => {
    const sheet = renderSheet();
    expect(sheet).toHaveAccessibleDescription('[العنوان]');
    const said = within(sheet).getByText(/عند النشر تصير البصيرة صفحةً عامة/);
    expect(said).toHaveTextContent('صفحةً عامة وصورةَ مشاركة يراهما أي شخص');
    expect(said).toHaveTextContent('ولا اسمك العام ومعرّفك إلا إن اخترتهما');
    expect(said).toHaveTextContent('لا تظهر فيها صورتك ولا موقعك ولا محادثتك');
    expect(said).toHaveTextContent('إلا ما نسخه غيرك قبل ذلك');
    expect(within(sheet).getByRole('button', { name: 'انشر وشارك' })).toBeEnabled();
    expect(within(sheet).queryByRole('button', { name: 'اسحب النشر' })).toBeNull();
    expect(within(sheet).queryByRole('link', { name: 'نزّل البطاقة' })).toBeNull();
  });

  it('offers the card as a download once the insight is public, and not after a withdrawal', async () => {
    mockApi({ [`DELETE /insights/${ID}/publication`]: { body: WITHDRAWN } });
    const sheet = renderSheet({ published: true });
    const download = within(sheet).getByRole('link', { name: 'نزّل البطاقة' });
    expect(download).toHaveAttribute('href', `${PATH}/card`);
    expect(download).toHaveAttribute('download', `tabsira-${ID}.png`);
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسحب النشر' }));
    await within(sheet).findByText(/سُحبت البصيرة/);
    expect(within(sheet).queryByRole('link', { name: 'نزّل البطاقة' })).toBeNull();
  });

  it('offers the map and the network inside sharing, each only while its feature is on, as separate choices', () => {
    const sheet = renderSheet({ publishTo: { atlas: true, community: true } });
    const more = within(sheet).getByRole('region', { name: 'طرق نشر أخرى' });
    expect(within(more).getByRole('link', { name: 'انشر على الخريطة' })).toHaveAttribute(
      'href',
      `/atlas/publish?insight=${ID}`
    );
    expect(within(more).getByRole('link', { name: 'انشر في تواصل' })).toHaveAttribute(
      'href',
      `/community/publish?insight=${ID}`
    );
    expect(within(more).getByText(/ولا يفعّل النشر في تواصل/)).toBeInTheDocument();
  });

  it('shows only the surface whose feature is on, and no section when neither is', () => {
    const sheet = renderSheet({ publishTo: { atlas: false, community: true } });
    expect(within(sheet).queryByRole('link', { name: 'انشر على الخريطة' })).toBeNull();
    expect(within(sheet).getByRole('link', { name: 'انشر في تواصل' })).toBeInTheDocument();
    sheet.remove();
    const bare = renderSheet();
    expect(within(bare).queryByRole('region', { name: 'طرق نشر أخرى' })).toBeNull();
    expect(within(bare).queryByRole('link')).toBeNull();
  });

  it('publishes, then hands the public address to the share dialog of the browser', async () => {
    const api = mockApi({ [`PUT /insights/${ID}/publication`]: { body: PUBLISHED } });
    const share = vi.fn().mockResolvedValue(undefined);
    stubShare(share);
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    await within(sheet).findByRole('button', { name: 'شارك الرابط' });
    expect(api.requests.map((request) => request.method)).toEqual(['PUT']);
    expect(share).toHaveBeenCalledWith({ title: '[العنوان]', url: URL_OF_PAGE });
    expect(within(sheet).getByText(URL_OF_PAGE)).toHaveAttribute('dir', 'ltr');
    expect(within(sheet).getByText(/هذه البصيرة منشورة الآن/)).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: 'اسحب النشر' })).toBeEnabled();
    expect(within(sheet).getByRole('link', { name: 'نزّل البطاقة' })).toHaveAttribute(
      'href',
      `${PATH}/card`
    );
  });

  it('copies the address when the browser has no share dialog, and says so', async () => {
    mockApi({ [`PUT /insights/${ID}/publication`]: { body: PUBLISHED } });
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubShare(undefined, { writeText });
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    expect(await within(sheet).findByText('نُسخ الرابط.')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(URL_OF_PAGE);
  });

  it('says nothing when the reader closes the share dialog', async () => {
    mockApi({ [`PUT /insights/${ID}/publication`]: { body: PUBLISHED } });
    const writeText = vi.fn();
    stubShare(vi.fn().mockRejectedValue(new DOMException('closed', 'AbortError')), { writeText });
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    await within(sheet).findByRole('button', { name: 'شارك الرابط' });
    expect(writeText).not.toHaveBeenCalled();
    expect(within(sheet).queryByText('نُسخ الرابط.')).toBeNull();
  });

  it('copies the address when the share dialog itself fails', async () => {
    mockApi({ [`PUT /insights/${ID}/publication`]: { body: PUBLISHED } });
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubShare(vi.fn().mockRejectedValue(new Error('not allowed')), { writeText });
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    expect(await within(sheet).findByText('نُسخ الرابط.')).toBeInTheDocument();
  });

  it('leaves the address on screen to copy by hand when nothing can copy it', async () => {
    mockApi({ [`PUT /insights/${ID}/publication`]: { body: PUBLISHED } });
    stubShare(undefined, undefined);
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    expect(await within(sheet).findByText(/تعذّر النسخ/)).toBeInTheDocument();
    expect(within(sheet).getByText(URL_OF_PAGE)).toBeInTheDocument();
  });

  it('treats a missing path in the answer as a failure, and builds no address itself', async () => {
    mockApi({ [`PUT /insights/${ID}/publication`]: { body: { ...PUBLISHED, path: null } } });
    const share = vi.fn();
    stubShare(share);
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('حدث خطأ من جهتنا');
    expect(share).not.toHaveBeenCalled();
    expect(within(sheet).getByRole('button', { name: 'انشر وشارك' })).toBeEnabled();
  });

  it('says in Arabic why an insight cannot be published, and stays unpublished', async () => {
    mockApi({
      [`PUT /insights/${ID}/publication`]: apiError(409, 'INSIGHT_NOT_PUBLISHABLE'),
    });
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('لا يمكن نشر هذه البصيرة');
    expect(within(sheet).getByRole('button', { name: 'انشر وشارك' })).toBeEnabled();
    expect(within(sheet).queryByRole('button', { name: 'اسحب النشر' })).toBeNull();
  });

  it('says what to do when the reader is a guest, or nothing answers', async () => {
    mockApi({ [`PUT /insights/${ID}/publication`]: apiError(401, 'UNAUTHORIZED') });
    const sheet = renderSheet();
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('انتهت جلستك');
    mockApi({ [`PUT /insights/${ID}/publication`]: 'network-error' });
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    await waitFor(() =>
      expect(within(sheet).getByRole('alert')).toHaveTextContent('تعذّر الوصول إلى تبصرة')
    );
  });

  it('starts from the published state and shares the known address without publishing again', async () => {
    const api = mockApi({});
    const share = vi.fn().mockResolvedValue(undefined);
    stubShare(share);
    const sheet = renderSheet({ published: true });
    expect(within(sheet).getByText(/هذه البصيرة منشورة الآن/)).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: 'شارك الرابط' }));
    await waitFor(() =>
      expect(share).toHaveBeenCalledWith({ title: '[العنوان]', url: URL_OF_PAGE })
    );
    expect(api.requests).toHaveLength(0);
    expect(within(sheet).getByText(URL_OF_PAGE)).toBeInTheDocument();
  });

  it('withdraws, takes the address away and goes back to what publishing would make public', async () => {
    const api = mockApi({ [`DELETE /insights/${ID}/publication`]: { body: WITHDRAWN } });
    const sheet = renderSheet({ published: true });
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسحب النشر' }));
    expect(await within(sheet).findByText(/سُحبت البصيرة/)).toBeInTheDocument();
    expect(api.requests.map((request) => request.method)).toEqual(['DELETE']);
    expect(within(sheet).getByRole('button', { name: 'انشر وشارك' })).toBeEnabled();
    expect(within(sheet).queryByRole('button', { name: 'اسحب النشر' })).toBeNull();
    expect(within(sheet).getByText(/عند النشر تصير البصيرة/)).toBeInTheDocument();
  });

  it('says when the withdrawal did not happen and keeps the insight published', async () => {
    mockApi({ [`DELETE /insights/${ID}/publication`]: 'network-error' });
    const sheet = renderSheet({ published: true });
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسحب النشر' }));
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('تعذّر الوصول إلى تبصرة');
    expect(within(sheet).getByRole('button', { name: 'اسحب النشر' })).toBeEnabled();
  });
});
