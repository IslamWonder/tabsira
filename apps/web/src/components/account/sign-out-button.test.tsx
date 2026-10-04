import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { SignOutButton } from './sign-out-button';

describe('SignOutButton', () => {
  it('signs out and tells the page', async () => {
    mockApi({ 'POST /auth/logout': { status: 204 } });
    const onSignedOut = vi.fn();
    render(<SignOutButton onSignedOut={onSignedOut} />);
    await userEvent.click(screen.getByRole('button', { name: 'اخرج' }));
    expect(onSignedOut).toHaveBeenCalledOnce();
  });

  it('keeps a failure under the button', async () => {
    mockApi({ 'POST /auth/logout': apiError(403, 'ORIGIN_NOT_ALLOWED') });
    render(<SignOutButton />);
    await userEvent.click(screen.getByRole('button', { name: 'اخرج' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('حدّث الصفحة');
  });
});
