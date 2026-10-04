import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PrivacyPage, { metadata as privacyMetadata } from './privacy/page';
import SupportPage, { metadata as supportMetadata } from './support/page';
import TermsPage, { metadata as termsMetadata } from './terms/page';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

describe('the three public legal pages', () => {
  it.each([
    ['/terms', 'شروط الاستخدام', TermsPage, termsMetadata],
    ['/privacy', 'سياسة الخصوصية', PrivacyPage, privacyMetadata],
    ['/support', 'الدعم', SupportPage, supportMetadata],
  ] as const)(
    '%s has its h1, canonical, indexing and structured data',
    (path, title, Page, metadata) => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 401 }));
      const { container } = render(<Page />);
      expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
      expect(metadata.alternates?.canonical).toBe(path);
      expect(metadata.robots).toMatchObject({ index: true, 'max-snippet': 0 });
      expect(String(metadata.title).length).toBeLessThanOrEqual(65);
      expect(String(metadata.description).length).toBeLessThanOrEqual(165);
      const data = JSON.parse(
        container.querySelector('script[type="application/ld+json"]')?.textContent ?? ''
      );
      expect(data).toMatchObject({ '@type': 'WebPage', url: `https://tabsira.test${path}` });
    }
  );

  it('support sends privacy requests to privacy@tabsira.me and says nothing is stored', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 401 }));
    render(<SupportPage />);
    expect(screen.getByRole('link', { name: 'privacy@tabsira.me' })).toHaveAttribute(
      'href',
      'mailto:privacy@tabsira.me'
    );
    expect(screen.getByText(/لا تحفظها تبصرة في قاعدة بياناتها/)).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'نموذج الدعم' })).toBeInTheDocument();
  });
});
