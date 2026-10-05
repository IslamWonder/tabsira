import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { HADITH_TEXT, IDENTITY, MY_POST, POST, QURAN_TEXT, sha256 } from '@/test/social';
import { PostCard, revealLabel } from './post-card';

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
    // Byte for byte: the UTF-8 bytes on screen are the bytes the API sent, and hash to what it said.
    expect(
      Buffer.from(quran?.textContent ?? '', 'utf8').equals(Buffer.from(QURAN_TEXT, 'utf8'))
    ).toBe(true);
    expect(
      Buffer.from(hadith?.textContent ?? '', 'utf8').equals(Buffer.from(HADITH_TEXT, 'utf8'))
    ).toBe(true);
    expect(sha256(quran?.textContent ?? '')).toBe(POST.insight.quran[0]?.sha256);
    expect(sha256(hadith?.textContent ?? '')).toBe(POST.insight.hadith[0]?.sha256);
    // The placeholders really would change under the usual damage, so the check above means something.
    expect(QURAN_TEXT.trim()).not.toBe(QURAN_TEXT);
    expect(QURAN_TEXT.normalize('NFC')).not.toBe(QURAN_TEXT);
    expect(HADITH_TEXT.replace(/\s+/g, ' ')).not.toBe(HADITH_TEXT);
    expect(HADITH_TEXT.length).toBeGreaterThan(280);
    // Neither text carries the verified chip: the Quran needs none, and a post's hadith none either.
    expect(screen.queryByText('نص موثّق من مصدره')).toBeNull();
    expect(screen.queryByText(/الدرر/)).toBeNull();
    expect(screen.queryByRole('link', { name: /تحقق/ })).toBeNull();
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
    expect(screen.getByText('تستند هذه البصيرة إلى الآية وحدها.')).toBeInTheDocument();
    // In a feed the reveal names what the post holds.
    render(
      <PostCard
        post={{ ...POST, insight: { ...POST.insight, hadith: [] } }}
        onChange={vi.fn()}
        headingLevel={3}
      />
    );
    expect(screen.getByRole('button', { name: 'اعرض الآية' })).toBeInTheDocument();
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
  it('shows only the handle when the author did not agree to show a full name (decision 64)', () => {
    guest();
    render(
      <PostCard
        post={{ ...POST, author: { handle: 'rain_reader', public_name: null } }}
        onChange={vi.fn()}
      />
    );
    const link = screen.getByRole('link', { name: 'صفحة @rain_reader' });
    expect(link).toHaveTextContent(/^@rain_reader$/);
    expect(screen.queryByText('[اسم عام]')).toBeNull();
  });

  it('asks a guest to sign in instead of reacting', async () => {
    guest();
    render(<PostCard post={POST} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /^انتفعتُ بها/ }));
    expect(screen.getByRole('status')).toHaveTextContent('ادخل لتتفاعل مع منشور أو تحفظه.');
    expect(screen.getByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fcommunity'
    );
  });

  it('reacts and saves through the API and shows what it kept', async () => {
    const onChange = vi.fn();
    const api = member({
      'PUT /posts/7345678901234567890/reactions/benefited': {
        body: { reactions: { benefited: 3, jazak: 1 }, mine: ['benefited'] },
      },
      'PUT /posts/7345678901234567890/bookmark': { status: 204 },
    });
    render(
      <PostCard
        post={{ ...POST, viewer: { reactions: [], bookmarked: false, is_author: false } }}
        onChange={onChange}
      />
    );
    await screen.findByRole('button', { name: /^انتفعتُ بها/ });
    await waitFor(() =>
      expect(api.requests.some((r) => r.url.endsWith('/me/public-identity'))).toBe(true)
    );
    await userEvent.click(screen.getByRole('button', { name: /^انتفعتُ بها/ }));
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ reactions: { benefited: 3, jazak: 1 } })
      )
    );
    expect(onChange.mock.lastCall?.[0].viewer).toEqual({
      reactions: ['benefited'],
      bookmarked: false,
      is_author: false,
    });
    await userEvent.click(screen.getByRole('button', { name: 'احفظ' }));
    await waitFor(() => expect(onChange.mock.lastCall?.[0].viewer.bookmarked).toBe(true));
  });

  it('shows both reactions with their public counts and presses the ones the reader gave', async () => {
    member({});
    render(
      <PostCard
        post={{
          ...POST,
          reactions: { benefited: 4, jazak: 0 },
          viewer: { reactions: ['benefited'], bookmarked: false, is_author: false },
        }}
        onChange={vi.fn()}
      />
    );
    const benefited = screen.getByRole('button', { name: 'انتفعتُ بها 4' });
    const thanks = screen.getByRole('button', { name: 'جزاك الله خيرًا' });
    expect(benefited).toHaveAttribute('aria-pressed', 'true');
    expect(thanks).toHaveAttribute('aria-pressed', 'false');
  });

  it('takes a reaction back with DELETE and keeps the other one', async () => {
    const onChange = vi.fn();
    const api = member({
      'DELETE /posts/7345678901234567890/reactions/benefited': {
        body: { reactions: { benefited: 1, jazak: 1 }, mine: ['jazak'] },
      },
    });
    render(
      <PostCard
        post={{
          ...POST,
          viewer: { reactions: ['benefited', 'jazak'], bookmarked: false, is_author: false },
        }}
        onChange={onChange}
      />
    );
    await waitFor(() =>
      expect(api.requests.some((r) => r.url.endsWith('/me/public-identity'))).toBe(true)
    );
    await userEvent.click(screen.getByRole('button', { name: /^انتفعتُ بها/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(onChange.mock.lastCall?.[0].viewer.reactions).toEqual(['jazak']);
    expect(onChange.mock.lastCall?.[0].reactions).toEqual({ benefited: 1, jazak: 1 });
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
        post={{ ...POST, viewer: { reactions: [], bookmarked: false, is_author: false } }}
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

  it('tells an unverified account to confirm its address, with no link, and shows a refused reaction', async () => {
    const onChange = vi.fn();
    mockApi({
      'GET /auth/me': { body: { ...USER, email_verified: false } },
    });
    render(<PostCard post={POST} onChange={onChange} />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^انتفعتُ بها/ })).toBeInTheDocument()
    );
    await userEvent.click(screen.getByRole('button', { name: /^انتفعتُ بها/ }));
    expect(await screen.findByRole('status')).toHaveTextContent('أكّد بريدك لتتفاعل مع المنشورات.');
    expect(screen.queryByRole('link', { name: 'ادخل' })).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('says when a reaction or a save is refused and keeps the post as it was', async () => {
    const onChange = vi.fn();
    const api = member({
      'DELETE /posts/7345678901234567890/reactions/jazak': apiError(429, 'RATE_LIMITED'),
      'DELETE /posts/7345678901234567890/bookmark': 'network-error',
    });
    render(
      <PostCard
        post={{
          ...POST,
          reactions: { benefited: 0, jazak: 1 },
          visibility: 'followers',
          viewer: { reactions: ['jazak'], bookmarked: true, is_author: false },
        }}
        onChange={onChange}
      />
    );
    await waitFor(() =>
      expect(api.requests.some((r) => r.url.endsWith('/me/public-identity'))).toBe(true)
    );
    expect(screen.getByText('للمتابعين')).toBeInTheDocument();
    const thanks = screen.getByRole('button', { name: /^جزاك الله خيرًا/ });
    expect(thanks).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(thanks);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'محفوظ' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/تعذّر/));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('comments on a card', () => {
  it('link to the thread with their count only while the social_comments feature is on', () => {
    guest();
    const { rerender } = render(<PostCard post={POST} onChange={vi.fn()} />);
    expect(document.querySelector('a[href$="#comments"]')).toBeNull();
    rerender(<PostCard post={POST} onChange={vi.fn()} comments />);
    expect(document.querySelector('a[href$="#comments"]')).not.toBeNull();
  });
});

describe('what a card leaves out', () => {
  it('names the reveal by what the post holds', () => {
    const only = (quran: number, hadith: number) => ({
      ...POST.insight,
      quran: POST.insight.quran.slice(0, quran),
      hadith: POST.insight.hadith.slice(0, hadith),
    });
    expect(revealLabel(only(1, 1))).toBe('اعرض الآية والحديث');
    expect(revealLabel(only(1, 0))).toBe('اعرض الآية');
    expect(revealLabel(only(0, 1))).toBe('اعرض الحديث');
    expect(revealLabel(only(0, 0))).toBe('اعرض الدليل');
  });

  it('shows no reflection block and no step when the post has none', () => {
    guest();
    render(
      <PostCard
        post={{ ...POST, reflection: null, insight: { ...POST.insight, step: null } }}
        onChange={vi.fn()}
      />
    );
    expect(screen.queryByRole('region', { name: 'كلمات الكاتب' })).toBeNull();
    expect(screen.queryByText(/خطوة/)).toBeNull();
  });

  it('shows the public photo on the full card only, from the address the API gave', () => {
    guest();
    const url = 'https://media.tabsira.test/public/0123456789abcdef0123456789abcdef.jpg';
    const withPhoto = { ...POST, insight: { ...POST.insight, has_photo: true, photo_url: url } };
    const { unmount } = render(<PostCard post={withPhoto} onChange={vi.fn()} variant="full" />);
    const photo = screen.getByRole('img', {
      name: 'صورة المشهد الذي وُلدت منه البصيرة «[عنوان البصيرة]»',
    });
    expect(photo).toHaveAttribute('src', url);
    expect(photo).toHaveAttribute('loading', 'lazy');
    unmount();

    render(<PostCard post={withPhoto} onChange={vi.fn()} />);
    expect(screen.queryByTestId('public-photo')).toBeNull();
  });

  it('shows no photo without an address, whatever the owner chose', () => {
    guest();
    render(
      <PostCard
        post={{ ...POST, insight: { ...POST.insight, has_photo: true, photo_url: null } }}
        onChange={vi.fn()}
        variant="full"
      />
    );
    expect(screen.queryByTestId('public-photo')).toBeNull();
  });
});
