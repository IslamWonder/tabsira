import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { COMMENT, POST, page, QURAN_TEXT } from '@/test/social';
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
});
