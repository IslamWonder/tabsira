import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { COMMENT, IDENTITY, MY_POST, POST, page, QURAN_TEXT } from '@/test/social';
import { PostScreen } from './post-screen';

vi.mock('next/navigation', () => ({ usePathname: () => `/posts/${POST.id}` }));

const guest = (routes = {}) =>
  mockApi({ 'GET /auth/me': apiError(401, 'UNAUTHORIZED'), ...routes });

describe('PostScreen', () => {
  it('shows the post with its evidence and its comments', async () => {
    guest({
      [`GET /posts/${POST.id}`]: { body: POST },
      [`GET /posts/${POST.id}/comments`]: { body: page([COMMENT]) },
    });
    render(<PostScreen postId={POST.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
    expect(document.querySelector('[data-scripture="quran"]')?.textContent).toBe(QURAN_TEXT);
    expect(await screen.findByText('[تعليق]')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'العودة إلى تواصل' })).toHaveAttribute(
      'href',
      '/community'
    );
  });

  it('tells a withdrawn post from one the viewer may not see', async () => {
    guest({ [`GET /posts/${POST.id}`]: apiError(410, 'GONE') });
    const { unmount } = render(<PostScreen postId={POST.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'سُحب هذا المنشور' })
    ).toBeInTheDocument();
    unmount();

    guest({ [`GET /posts/${POST.id}`]: apiError(404, 'NOT_FOUND') });
    render(<PostScreen postId={POST.id} />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'لم نجد هذا المنشور' })
    ).toBeInTheDocument();
  });

  it('says when the post cannot be loaded and tries again', async () => {
    guest({ [`GET /posts/${POST.id}`]: 'network-error' });
    render(<PostScreen postId={POST.id} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/تعذّر الوصول/);
    guest({
      [`GET /posts/${POST.id}`]: { body: POST },
      [`GET /posts/${POST.id}/comments`]: { body: page([]) },
    });
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' })
    ).toBeInTheDocument();
  });

  it('keeps what a reaction changed, and ends with the author withdrawing the post', async () => {
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [`GET /posts/${POST.id}`]: { body: MY_POST },
      [`GET /posts/${POST.id}/comments`]: { body: page([]) },
      [`PUT /posts/${POST.id}/like`]: { body: { liked: true, like_count: 3 } },
      [`DELETE /posts/${POST.id}`]: { status: 204 },
    });
    render(<PostScreen postId={POST.id} />);
    await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' });
    await waitFor(() => expect(screen.getByLabelText('اكتب تعليقًا')).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: /^أثر/ }));
    expect(await screen.findByText('3 آثار')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'اسحب المنشور' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'اسحب' }));
    expect(await screen.findByRole('status')).toHaveTextContent('سُحب المنشور من تواصل.');
    expect(screen.getAllByRole('link', { name: 'العودة إلى تواصل' })).toHaveLength(2);
  });

  it("shows the author's own unpublished post without comments, and hides it once its author is blocked from a comment", async () => {
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [`GET /posts/${POST.id}`]: { body: { ...MY_POST, status: 'pending_review' } },
    });
    const { unmount } = render(<PostScreen postId={POST.id} />);
    await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' });
    expect(screen.queryByRole('heading', { name: 'التعليقات' })).toBeNull();
    unmount();

    const byAuthor = { ...COMMENT, author: POST.author, body: '[تعليق الكاتب]' };
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [`GET /posts/${POST.id}`]: { body: POST },
      [`GET /posts/${POST.id}/comments`]: { body: page([byAuthor]) },
      'PUT /blocks/rain_reader': { status: 204 },
    });
    render(<PostScreen postId={POST.id} />);
    const comment = (await screen.findByText('[تعليق الكاتب]')).closest(
      '[data-comment-id]'
    ) as HTMLElement;
    await waitFor(() =>
      expect(within(comment).getByRole('button', { name: 'احجب' })).toBeInTheDocument()
    );
    await userEvent.click(within(comment).getByRole('button', { name: 'احجب' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'احجب' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'لم نجد هذا المنشور' })
    ).toBeInTheDocument();
  });

  it('shows nothing of the post once its author is blocked from the card itself', async () => {
    mockApi({
      'GET /auth/me': { body: USER },
      'GET /me/public-identity': { body: IDENTITY },
      [`GET /posts/${POST.id}`]: { body: POST },
      [`GET /posts/${POST.id}/comments`]: { body: page([]) },
      'PUT /blocks/rain_reader': { status: 204 },
    });
    render(<PostScreen postId={POST.id} />);
    await screen.findByRole('heading', { level: 1, name: '[عنوان البصيرة]' });
    await waitFor(() => expect(screen.getByLabelText('اكتب تعليقًا')).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: 'المزيد' }));
    await userEvent.click(screen.getByRole('button', { name: 'احجب [اسم عام]' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'احجب' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'لم نجد هذا المنشور' })
    ).toBeInTheDocument();
  });

  it('ignores an answer that arrives after the screen is gone', async () => {
    let answer: (() => void) | null = null;
    guest({
      [`GET /posts/${POST.id}`]: () =>
        new Promise((resolve) => {
          answer = () => resolve({ body: POST });
        }),
    });
    const { unmount } = render(<PostScreen postId={POST.id} />);
    await waitFor(() => expect(answer).not.toBeNull());
    unmount();
    (answer as unknown as () => void)();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('heading')).toBeNull();
  });
});
