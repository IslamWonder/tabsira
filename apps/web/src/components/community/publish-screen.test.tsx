import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { REFLECTION_MAX } from '@/social/types';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { insightOut } from '@/test/scan';
import { IDENTITY, MY_POST, NO_IDENTITY } from '@/test/social';
import { PublishScreen } from './publish-screen';

const params = { insight: '7000000000000000001' as string | null };
vi.mock('next/navigation', () => ({
  usePathname: () => '/community/publish',
  useSearchParams: () => ({ get: (key: string) => (key === 'insight' ? params.insight : null) }),
}));

const DRAFT = { ...MY_POST, status: 'draft' as const, published_at: null };

function member(extra: Record<string, Route> = {}, identity: object = IDENTITY) {
  return mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: identity },
    ...extra,
  });
}

describe('PublishScreen', () => {
  it('asks for an insight when none is named', () => {
    params.insight = null;
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    render(<PublishScreen />);
    expect(screen.getByRole('heading', { level: 1, name: 'اختر بصيرة أولًا' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'افتح عالمي' })).toHaveAttribute('href', '/world');
    params.insight = '7000000000000000001';
  });

  it('sends a guest to sign in and comes back to the same insight', async () => {
    mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED') });
    render(<PublishScreen />);
    expect(await screen.findByRole('link', { name: 'ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fcommunity%2Fpublish%3Finsight%3D7000000000000000001'
    );
  });

  it('asks for a public identity first, and takes it right there', async () => {
    member({ 'PUT /me/public-identity': { body: IDENTITY } }, NO_IDENTITY);
    render(<PublishScreen />);
    expect(await screen.findByText('اختر هويتك العامة قبل أن تنشر.')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('المعرّف'), 'reader');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ هويتي' }));
    expect(await screen.findByRole('button', { name: 'أنشئ المسودة' })).toBeInTheDocument();
  });

  it('makes a draft, previews it, submits it and tells the outcome', async () => {
    const api = member({
      'POST /posts': { status: 201, body: DRAFT },
      [`POST /posts/${DRAFT.id}/submit`]: {
        body: { ...DRAFT, status: 'pending_review', status_message: '[يراجعه مشرف]' },
      },
    });
    render(<PublishScreen />);
    const reflection = await screen.findByLabelText('كلماتك (اختياري)');
    await userEvent.type(reflection, 'ما تعلمته');
    await userEvent.click(screen.getByRole('radio', { name: 'للمتابعين' }));
    await userEvent.click(screen.getByRole('button', { name: 'أنشئ المسودة' }));
    expect(await screen.findByText(/أُنشئت المسودة/)).toBeInTheDocument();
    expect(await api.bodies('POST', '/posts')).toEqual([
      {
        insight_id: '7000000000000000001',
        reflection: 'ما تعلمته',
        visibility: 'followers',
        photo: false,
      },
    ]);
    expect(screen.getByRole('heading', { level: 2, name: 'هكذا يظهر منشورك' })).toBeInTheDocument();
    expect(screen.getByText('مسودة')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'انشر' }));
    expect(await screen.findByText(/ويراجعها مشرف/)).toBeInTheDocument();
    expect(screen.getByText('قيد المراجعة')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'افتح المنشور' })).toHaveAttribute(
      'href',
      `/posts/${DRAFT.id}`
    );
  });

  it('says why an insight cannot be published, and edits a refused post into a draft again', async () => {
    const api = member({
      'POST /posts': apiError(409, 'INSIGHT_NOT_PUBLISHABLE'),
    });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/لا يمكن نشر هذه البصيرة/);

    member({
      'POST /posts': {
        status: 201,
        body: { ...DRAFT, status: 'rejected', status_message: '[لم يُقبل]' },
      },
      [`PATCH /posts/${DRAFT.id}`]: {
        body: {
          ...DRAFT,
          reflection: {
            text: 'كلمات أخرى',
            source: 'user',
            verified: false,
            looks_like_scripture: false,
          },
        },
      },
    });
    await userEvent.click(screen.getByRole('button', { name: 'أنشئ المسودة' }));
    expect(await screen.findByText('لم يُقبل')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'عدّل المسودة' }));
    const field = screen.getByLabelText('كلماتك (اختياري)');
    await userEvent.clear(field);
    await userEvent.type(field, 'كلمات أخرى');
    await userEvent.click(screen.getByRole('button', { name: 'احفظ التعديل' }));
    expect(await screen.findByText('حُفظ التعديل.')).toBeInTheDocument();
    expect(screen.getByText('كلمات أخرى')).toBeInTheDocument();
    expect(api.requests).toBeDefined();
  });

  it('withdraws a draft from the preview', async () => {
    member({
      'POST /posts': { status: 201, body: DRAFT },
      [`DELETE /posts/${DRAFT.id}`]: { status: 204 },
    });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    await userEvent.click(await screen.findByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'احذف المسودة' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب' }));
    await waitFor(() => expect(screen.getByText('سُحب المنشور من تواصل.')).toBeInTheDocument());
  });

  it('offers the photo only when the insight kept one, off by default, for a public post', async () => {
    const kept = insightOut({
      id: '7000000000000000001',
      image: { sensitive: false, url: null, has_photo: true },
    });
    const api = member({
      'GET /insights/7000000000000000001': { body: kept },
      'POST /posts': { status: 201, body: DRAFT },
    });
    render(<PublishScreen />);
    const box = await screen.findByRole('checkbox', { name: 'أرفق الصورة' });
    expect(box).not.toBeChecked();
    expect(box).toHaveAccessibleDescription(/تصير صورة مشهدك عامة مع المنشور/);
    // A post for followers never shows the photo, so the choice is not offered there.
    await userEvent.click(screen.getByRole('radio', { name: 'للمتابعين' }));
    expect(screen.queryByRole('checkbox', { name: 'أرفق الصورة' })).toBeNull();
    await userEvent.click(screen.getByRole('radio', { name: 'للجميع' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'أرفق الصورة' }));
    await userEvent.click(screen.getByRole('button', { name: 'أنشئ المسودة' }));
    expect(await api.bodies('POST', '/posts')).toEqual([
      { insight_id: '7000000000000000001', reflection: null, visibility: 'public', photo: true },
    ]);
  });

  it('ticks the photo then chooses followers: the choice is not sent', async () => {
    const api = member({
      'GET /insights/7000000000000000001': {
        body: insightOut({ image: { sensitive: false, url: null, has_photo: true } }),
      },
      'POST /posts': { status: 201, body: DRAFT },
    });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('checkbox', { name: 'أرفق الصورة' }));
    await userEvent.click(screen.getByRole('radio', { name: 'للمتابعين' }));
    await userEvent.click(screen.getByRole('button', { name: 'أنشئ المسودة' }));
    expect(await api.bodies('POST', '/posts')).toEqual([
      {
        insight_id: '7000000000000000001',
        reflection: null,
        visibility: 'followers',
        photo: false,
      },
    ]);
  });

  it('offers no photo when none is kept, or when the insight cannot be read', async () => {
    member({
      'GET /insights/7000000000000000001': {
        body: insightOut({ image: { sensitive: false, url: null, has_photo: false } }),
      },
    });
    render(<PublishScreen />);
    await screen.findByRole('button', { name: 'أنشئ المسودة' });
    expect(screen.queryByRole('checkbox', { name: 'أرفق الصورة' })).toBeNull();

    member({ 'GET /insights/7000000000000000001': apiError(404, 'NOT_FOUND') });
    render(<PublishScreen />);
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: 'أنشئ المسودة' })).toHaveLength(2)
    );
    expect(screen.queryByRole('checkbox', { name: 'أرفق الصورة' })).toBeNull();
  });

  it('asks an unverified account to verify its address first', async () => {
    member({ 'GET /auth/me': { body: { ...USER, email_verified: false } } });
    render(<PublishScreen />);
    expect(await screen.findByText(messages.community.publish.verify)).toBeInTheDocument();
  });

  it.each([
    ['SERVICE_UNAVAILABLE', 503, messages.community.publish.unavailable],
    ['PUBLIC_IDENTITY_REQUIRED', 409, messages.community.publish.identityFirst],
  ])('says what %s means when the draft cannot be made', async (code, status, text) => {
    member({ 'POST /posts': apiError(status, code) });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
  });

  it('falls back to the general message for any other refusal', async () => {
    member({ 'POST /posts': apiError(500, 'INTERNAL') });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('sends nothing when the words are over the limit', async () => {
    const api = member();
    render(<PublishScreen />);
    const field = await screen.findByLabelText('كلماتك (اختياري)');
    fireEvent.change(field, { target: { value: 'ا'.repeat(REFLECTION_MAX + 1) } });
    fireEvent.submit(field.closest('form') as HTMLFormElement);
    expect(api.requests.filter((r) => r.method === 'POST')).toHaveLength(0);
  });

  it('tells a refused outcome, and a published one', async () => {
    member({
      'POST /posts': { status: 201, body: DRAFT },
      [`POST /posts/${DRAFT.id}/submit`]: {
        body: { ...DRAFT, status: 'rejected', status_message: '[لم يُقبل]' },
      },
    });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    await userEvent.click(await screen.findByRole('button', { name: 'انشر' }));
    expect(
      await screen.findByText(messages.community.publish.outcome.rejected)
    ).toBeInTheDocument();
  });

  it('tells a published outcome', async () => {
    member({
      'POST /posts': { status: 201, body: DRAFT },
      [`POST /posts/${DRAFT.id}/submit`]: { body: { ...DRAFT, status: 'published' } },
    });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    await userEvent.click(await screen.findByRole('button', { name: 'انشر' }));
    expect(
      await screen.findByText(messages.community.publish.outcome.published)
    ).toBeInTheDocument();
  });

  it('shows a failed submit under the preview, and leaves an edit unsaved on cancel', async () => {
    member({
      'POST /posts': { status: 201, body: DRAFT },
      [`POST /posts/${DRAFT.id}/submit`]: apiError(500, 'INTERNAL'),
    });
    render(<PublishScreen />);
    await userEvent.click(await screen.findByRole('button', { name: 'أنشئ المسودة' }));
    await userEvent.click(await screen.findByRole('button', { name: 'انشر' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'عدّل المسودة' }));
    await userEvent.click(
      screen.getByRole('button', { name: messages.community.publish.cancelEdit })
    );
    expect(screen.getByRole('heading', { level: 2, name: 'هكذا يظهر منشورك' })).toBeInTheDocument();
  });
});
