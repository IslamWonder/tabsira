import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SaveInvitation } from './save-invitation';

describe('SaveInvitation', () => {
  it('asks softly, with two equal answers', async () => {
    const onContinueAsGuest = vi.fn();
    render(<SaveInvitation returnTo="/world" onContinueAsGuest={onContinueAsGuest} />);
    expect(
      screen.getByRole('region', { name: 'هل تحفظ ما تعلّمته لنواصل من هنا؟' })
    ).toBeInTheDocument();
    const save = screen.getByRole('link', { name: 'احفظ مساري' });
    expect(save).toHaveAttribute('href', '/signup?next=%2Fworld');
    const guest = screen.getByRole('button', { name: 'أتابع كضيف' });
    // Equal weight: the same look for both answers, no pressure (tajriba LUX-28).
    expect(save.className).toBe(guest.className);
    await userEvent.click(guest);
    expect(onContinueAsGuest).toHaveBeenCalledOnce();
  });
});
