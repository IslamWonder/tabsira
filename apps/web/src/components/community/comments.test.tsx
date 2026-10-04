import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { USER } from '@/test/fixtures';
import { COMMENT, IDENTITY, NO_IDENTITY, page } from '@/test/social';
import { Comments } from './comments';

vi.mock('next/navigation', () => ({ usePathname: () => '/posts/1' }));

const POST_ID = '7345678901234567890';
const MINE = {
  ...COMMENT,
  id: '7345678901234567892',
  author: IDENTITY,
  body: '[تعليقي]',
  is_mine: true,
};
const REPLY = { ...COMMENT, id: '7345678901234567893', body: '[رد]' };

function member(extra: Record<string, Route> = {}, identity: object = IDENTITY) {
  return mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: identity },
    [`GET /posts/${POST_ID}/comments`]: { body: page([{ ...COMMENT, replies: [REPLY] }, MINE]) },
    ...extra,
  });
}

describe('Comments', () => {
  it('lists the thread with its replies, and gates a guest', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /posts/${POST_ID}/comments`]: { body: page([{ ...COMMENT, replies: [REPLY] }]) },
    });
    render(<Comments postId={POST_ID} />);
    expect(await screen.findByText('[تعليق]')).toBeInTheDocument();
    expect(screen.getByText('[رد]')).toBeInTheDocument();
    expect(screen.getByLabelText('اكتب تعليقًا')).toBeDisabled();
    expect(screen.getByText('ادخل لتعلّق.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'ردّ' })).toBeNull();
  });

  it('asks a verified member without a public identity to choose one', async () => {
    member({}, NO_IDENTITY);
    render(<Comments postId={POST_ID} />);
    expect(await screen.findByRole('link', { name: 'اختر اسمك العام' })).toHaveAttribute(
      'href',
      '/me#identity'
    );
    expect(screen.getByLabelText('اكتب تعليقًا')).toBeDisabled();
  });

  it('sends a comment and a reply, shows them with the state the guard gave, and deletes its own', async () => {
    const api = member({
      [`POST /posts/${POST_ID}/comments`]: async (request) => {
        const body = (await request.json()) as { body: string; parent_id: string | null };
        return {
          status: 201,
          body: {
            ...MINE,
            id: body.parent_id === null ? '9000000000000000001' : '9000000000000000002',
            body: body.body,
            status: 'pending_review',
            status_message: '[يراجعه مشرف]',
          },
        };
      },
      [`DELETE /posts/${POST_ID}/comments/${MINE.id}`]: { status: 204 },
    });
    render(<Comments postId={POST_ID} />);
    await screen.findByText('[تعليق]');
    await waitFor(() => expect(screen.getByLabelText('اكتب تعليقًا')).toBeEnabled());

    await userEvent.type(screen.getByLabelText('اكتب تعليقًا'), 'تعليق جديد');
    await userEvent.click(screen.getByRole('button', { name: 'أرسل' }));
    expect(await screen.findByText('تعليق جديد')).toBeInTheDocument();
    expect(screen.getAllByText('[يراجعه مشرف]')).toHaveLength(1);
    expect(screen.getByText('قيد المراجعة')).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole('button', { name: 'ردّ' })[0] as HTMLElement);
    await userEvent.type(screen.getByLabelText('اكتب ردًا على [عضو آخر]'), 'رد جديد');
    await userEvent.click(screen.getAllByRole('button', { name: 'أرسل' })[1] as HTMLElement);
    expect(await screen.findByText('رد جديد')).toBeInTheDocument();
    expect(await api.bodies('POST', `/posts/${POST_ID}/comments`)).toEqual([
      { body: 'تعليق جديد', parent_id: null },
      { body: 'رد جديد', parent_id: COMMENT.id },
    ]);

    const mine = screen.getByText('[تعليقي]').closest('[data-comment-id]') as HTMLElement;
    await userEvent.click(within(mine).getByRole('button', { name: 'احذف' }));
    await waitFor(() => expect(screen.queryByText('[تعليقي]')).toBeNull());
    expect(screen.getByText('حُذف تعليقك.')).toBeInTheDocument();
  });

  it("removes a blocked member's comments and replies from the thread", async () => {
    member({ 'PUT /blocks/other_one': { status: 204 } });
    render(<Comments postId={POST_ID} />);
    await screen.findByText('[تعليق]');
    const thread = screen.getByText('[تعليق]').closest('[data-comment-id]') as HTMLElement;
    await userEvent.click(within(thread).getByRole('button', { name: 'احجب' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'احجب' }));
    await waitFor(() => expect(screen.queryByText('[تعليق]')).toBeNull());
    expect(screen.queryByText('[رد]')).toBeNull();
    expect(screen.getByText('[تعليقي]')).toBeInTheDocument();
  });

  it('says when the comments cannot be loaded, and when there are none', async () => {
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /posts/${POST_ID}/comments`]: 'network-error',
    });
    render(<Comments postId={POST_ID} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    mockApi({
      'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
      [`GET /posts/${POST_ID}/comments`]: { body: page([]) },
    });
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByText('لا تعليقات بعد.')).toBeInTheDocument();
  });
});
