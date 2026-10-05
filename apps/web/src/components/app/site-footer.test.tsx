import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SiteFooter } from './site-footer';

const where = vi.hoisted(() => ({ pathname: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => where.pathname }));

describe('SiteFooter', () => {
  it('links the site pages under every page but the world, which fills the screen', () => {
    where.pathname = '/community';
    const { unmount } = render(<SiteFooter />);
    expect(screen.getByRole('link', { name: 'سياسة الخصوصية' })).toBeInTheDocument();
    unmount();

    where.pathname = '/world';
    const { container } = render(<SiteFooter />);
    expect(container).toBeEmptyDOMElement();
  });
});
