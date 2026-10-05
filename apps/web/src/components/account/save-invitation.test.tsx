import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SaveInvitation } from './save-invitation';

describe('SaveInvitation', () => {
  it('asks for an account, or a sign-in, and has no way to go on as a guest (decision 64)', () => {
    render(<SaveInvitation returnTo="/world" />);
    expect(
      screen.getByRole('region', { name: 'هل تحفظ ما تعلّمته لنواصل من هنا؟' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'أنشئ حسابي واحفظ بصيرتي' })).toHaveAttribute(
      'href',
      '/signup?next=%2Fworld'
    );
    expect(screen.getByRole('link', { name: 'لي حساب: ادخل' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fworld'
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByText('أتابع كضيف')).toBeNull();
  });
});
