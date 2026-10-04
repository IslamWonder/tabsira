import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
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
    await userEvent.type(screen.getByLabelText('الاسم العام'), 'قارئ');
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
});
