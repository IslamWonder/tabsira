import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { HADITH_TEXT, IDENTITY, MY_POST, POST, QURAN_TEXT, sha256 } from '@/test/social';
import { PostCard } from './post-card';

vi.mock('next/navigation', () => ({ usePathname: () => '/community' }));

const guest = () => mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
const member = (extra = {}) =>
  mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: IDENTITY },
    ...extra,
  });

describe('PostCard and the scripture it shows', () => {
  it('shows the verse and the hadith byte for byte, behind a reveal in a feed', async () => {
    guest();
    render(<PostCard post={POST} onChange={vi.fn()} />);
    expect(screen.queryByTestId('post-evidence')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'اعرض الآية والحديث' }));
    const quran = document.querySelector('[data-scripture="quran"]');
    const hadith = document.querySelector('[data-scripture="hadith"]');
    expect(quran?.textContent).toBe(QURAN_TEXT);
    expect(hadith?.textContent).toBe(HADITH_TEXT);
    // What is on screen hashes to what the API said it sent: nothing was changed on the way.
    expect(sha256(quran?.textContent ?? '')).toBe(POST.insight.quran[0]?.sha256);
    expect(sha256(hadith?.textContent ?? '')).toBe(POST.insight.hadith[0]?.sha256);
    expect(screen.getAllByText('نص موثّق من مصدره')).toHaveLength(2);
    expect(screen.getByRole('link', { name: /تحقق في الدرر/ })).toHaveAttribute(
      'href',
      'https://dorar.net/'
    );
  });

  it('shows the evidence at once on its own page, and says when the verse stands alone', () => {
    guest();
    render(
      <PostCard
        post={{ ...POST, insight: { ...POST.insight, hadith: [] } }}
        onChange={vi.fn()}
        variant="full"
        headingLevel={1}
      />
    );
    expect(screen.getByTestId('post-evidence')).toBeInTheDocument();
    expect(screen.getByText(/تُعرض الآية وحدها/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '[عنوان البصيرة]' })).toBeInTheDocument();
  });

  it("labels the author's words as theirs and never as verified", () => {
    guest();
    render(
      <PostCard
        post={{
          ...POST,
          reflection: {
            text: '[نص يشبه آية]',
            source: 'user',
            verified: false,
            looks_like_scripture: true,
          },
        }}
        onChange={vi.fn()}
      />
    );
    const reflection = screen.getByRole('region', { name: 'كلمات الكاتب' });
    expect(within(reflection).getByText('[نص يشبه آية]')).toHaveAttribute('data-source', 'user');
    expect(within(reflection).getByText(/يبدو هذا النص كآية أو حديث/)).toBeInTheDocument();
    expect(within(reflection).queryByText('نص موثّق من مصدره')).toBeNull();
  });
});

describe('PostCard reactions', () => {
  it('asks a guest to sign in instead of liking', async () => {
    guest();
    render(<PostCard post={POST} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /^أثر/ }));
    expect(screen.getByRole('status')).toHaveTextContent('ادخل لتترك أثرًا أو تحفظ منشورًا.');
    expect(screen.getByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fcommunity'
    );
  });

  it('likes and saves through the API and shows what it kept', async () => {
    const onChange = vi.fn();
    const api = member({
      'PUT /posts/7345678901234567890/like': { body: { liked: true, like_count: 3 } },
      'PUT /posts/7345678901234567890/bookmark': { status: 204 },
    });
    render(
      <PostCard
        post={{ ...POST, viewer: { liked: false, bookmarked: false, is_author: false } }}
        onChange={onChange}
      />
    );
    await screen.findByRole('button', { name: /^أثر/ });
    await waitFor(() =>
      expect(api.requests.some((r) => r.url.endsWith('/me/public-identity'))).toBe(true)
    );
    await userEvent.click(screen.getByRole('button', { name: /^أثر/ }));
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ like_count: 3 }))
    );
    expect(onChange.mock.lastCall?.[0].viewer).toEqual({
      liked: true,
      bookmarked: false,
      is_author: false,
    });
    await userEvent.click(screen.getByRole('button', { name: 'احفظ' }));
    await waitFor(() => expect(onChange.mock.lastCall?.[0].viewer.bookmarked).toBe(true));
  });

  it('tells the author the state only they see, and lets them withdraw', async () => {
    const onRemoved = vi.fn();
    member({ 'DELETE /posts/7345678901234567890': { status: 204 } });
    render(
      <PostCard
        post={{
          ...MY_POST,
          status: 'pending_review',
          status_message: '[يحتاج إلى مراجعة]',
        }}
        onChange={vi.fn()}
        onRemoved={onRemoved}
      />
    );
    const status = screen.getByTestId('post-status');
    expect(within(status).getByText('قيد المراجعة')).toBeInTheDocument();
    expect(within(status).getByText('[يحتاج إلى مراجعة]')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب المنشور' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب' }));
    await waitFor(() => expect(onRemoved).toHaveBeenCalledWith('withdrawn'));
  });

  it("reports a stranger's post with one of the API's reasons, and blocks its author", async () => {
    const onRemoved = vi.fn();
    const api = member({
      'POST /reports': { status: 201, body: { id: '1' } },
      'PUT /blocks/rain_reader': { status: 204 },
    });
    render(
      <PostCard
        post={{ ...POST, viewer: { liked: false, bookmarked: false, is_author: false } }}
        onChange={vi.fn()}
        onRemoved={onRemoved}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'بلّغ' }));
    await userEvent.click(screen.getByRole('radio', { name: 'نسبة قول ديني إلى غير قائله' }));
    await userEvent.type(screen.getByLabelText(/تفاصيل تساعد المشرف/), 'تفاصيل للمشرف');
    await userEvent.click(screen.getByRole('button', { name: 'أرسل البلاغ' }));
    expect(await screen.findByText('وصل بلاغك، وسيراجعه مشرف.')).toBeInTheDocument();
    expect(await api.bodies('POST', '/reports')).toEqual([
      {
        target_type: 'post',
        target_id: POST.id,
        reason: 'false_religious_claim',
        details: 'تفاصيل للمشرف',
      },
    ]);
    await userEvent.click(screen.getByRole('button', { name: 'أغلق' }));
    await userEvent.click(screen.getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'احجب [اسم عام]' }));
    await userEvent.click(screen.getByRole('button', { name: 'احجب' }));
    expect(await screen.findByText(/حجبت هذا العضو/)).toBeInTheDocument();
    expect(onRemoved).toHaveBeenCalledWith('blocked');
  });

  it('explains «لماذا أرى هذا؟» with the reason and the four inputs', async () => {
    guest();
    render(
      <PostCard
        post={{ ...POST, why: { code: 'fresh', text: '[نُشر قبل قليل]' } }}
        onChange={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: /لماذا أرى هذا؟/ }));
    const sheet = screen.getByRole('dialog');
    expect(within(sheet).getByText('[نُشر قبل قليل]')).toBeInTheDocument();
    expect(within(sheet).getAllByRole('listitem')).toHaveLength(4);
    expect(within(sheet).getByRole('link', { name: 'افتح «ملفي»' })).toHaveAttribute(
      'href',
      '/me#settings'
    );
  });
});
