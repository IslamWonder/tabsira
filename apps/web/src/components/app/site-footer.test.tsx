import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { setSignedIn } from '@/account/session';
import { USER } from '@/test/fixtures';
import { SiteFooter } from './site-footer';

const where = vi.hoisted(() => ({ pathname: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => where.pathname }));

describe('SiteFooter', () => {
  it('links the site pages under every page but the world, which fills the screen', () => {
    where.pathname = '/community';
    const { unmount } = render(<SiteFooter />);
    expect(screen.getByRole('heading', { name: 'استكشف تبصرة' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'المساعدة والسياسات' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'كيف تعمل؟' })).toHaveAttribute('href', '/#how');
    expect(screen.getByRole('link', { name: 'سياسة الخصوصية' })).toBeInTheDocument();
    unmount();

    where.pathname = '/world';
    const { container } = render(<SiteFooter />);
    expect(container).toBeEmptyDOMElement();
  });

  it('leaves the example out for an account that holds an insight of its own', () => {
    where.pathname = '/community';
    const { unmount } = render(<SiteFooter />);
    expect(screen.getByRole('link', { name: 'جرّب بصيرة' })).toHaveAttribute('href', '/#example');
    unmount();

    setSignedIn({ ...USER, has_own_insight: true });
    render(<SiteFooter />);
    expect(screen.queryByRole('link', { name: 'جرّب بصيرة' })).toBeNull();
    expect(screen.getByRole('link', { name: 'كيف تعمل؟' })).toBeInTheDocument();
  });

  it('stays under the analysis on a phone, and leaves the full-screen analysis alone from tablet up', () => {
    where.pathname = '/scan/117388953510985201';
    const { container, unmount } = render(<SiteFooter />);
    expect(container.querySelector('footer')).toHaveClass('tablet:hidden');
    unmount();

    where.pathname = '/community';
    const other = render(<SiteFooter />);
    expect(other.container.querySelector('footer')).not.toHaveClass('tablet:hidden');
  });
});
