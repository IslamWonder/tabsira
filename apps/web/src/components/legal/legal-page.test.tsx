import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { legalMessages } from '@/messages/legal';
import { JsonLd } from './json-ld';
import { LegalPage } from './legal-page';
import { RichText } from './rich-text';

const { terms, privacy } = legalMessages();
const SEO = { path: '/terms', title: terms.title, description: terms.description } as const;

describe('RichText', () => {
  it('links an address left to right and isolates a Latin name', () => {
    const { container } = render(
      <p>
        <RichText text="راسل privacy@tabsira.me عن Google Analytics الآن" />
      </p>
    );
    const link = screen.getByRole('link', { name: 'privacy@tabsira.me' });
    expect(link).toHaveAttribute('href', 'mailto:privacy@tabsira.me');
    expect(link).toHaveAttribute('dir', 'ltr');
    expect(container.querySelector('bdi')?.textContent).toBe('Google Analytics');
    expect(container.textContent).toBe('راسل privacy@tabsira.me عن Google Analytics الآن');
  });

  it('leaves plain Arabic alone', () => {
    const { container } = render(
      <p>
        <RichText text="نص عربي فقط" />
      </p>
    );
    expect(container.textContent).toBe('نص عربي فقط');
    expect(container.querySelector('a, bdi')).toBeNull();
  });
});

describe('JsonLd', () => {
  it('prints the data and can never close its own script', () => {
    const { container } = render(<JsonLd data={{ name: '</script><b>' }} />);
    const script = container.querySelector('script[type="application/ld+json"]');
    expect(script?.innerHTML).not.toContain('</script>');
    expect(JSON.parse(script?.textContent ?? '')).toEqual({ name: '</script><b>' });
  });
});

describe('LegalPage', () => {
  it('has one h1, the version and the date, and WebPage data', () => {
    const { container } = render(<LegalPage document={terms} seo={SEO} />);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'شروط الاستخدام' })).toBeInTheDocument();
    expect(screen.getByText('النسخة 2026-10-05T18:00Z')).toBeInTheDocument();
    expect(container.querySelector('time')).toHaveAttribute('datetime', '2026-10-05T18:00Z');
    const data = JSON.parse(
      container.querySelector('script[type="application/ld+json"]')?.textContent ?? ''
    );
    expect(data).toMatchObject({ '@type': 'WebPage', dateModified: '2026-10-05T18:00Z' });
  });

  it('anchors every section and lists each one in the table of contents', () => {
    const { container } = render(
      <LegalPage document={privacy} seo={{ ...SEO, path: '/privacy' }} />
    );
    for (const section of privacy.sections) {
      const target = container.querySelector(`section#${section.id}`);
      expect(target).not.toBeNull();
      expect(within(target as HTMLElement).getByRole('heading', { level: 2 })).toHaveTextContent(
        section.heading
      );
      for (const link of screen.getAllByRole('link', { name: section.heading })) {
        expect(link).toHaveAttribute('href', `#${section.id}`);
      }
    }
  });

  it('keeps a table of contents for the phone, folded, and one for larger screens', () => {
    const { container } = render(<LegalPage document={terms} seo={SEO} />);
    expect(screen.getAllByRole('navigation', { name: 'فهرس الصفحة' })).toHaveLength(2);
    expect(container.querySelector('details')).not.toHaveAttribute('open');
  });

  it('links the other pages, never itself', () => {
    render(<LegalPage document={terms} seo={SEO} />);
    const related = screen.getByRole('navigation', { name: 'صفحات ذات صلة' });
    expect(
      within(related)
        .getAllByRole('link')
        .map((link) => link.getAttribute('href'))
    ).toEqual(['/privacy', '/support', '/sources']);
  });

  it('renders lists as lists and addresses as links', () => {
    render(<LegalPage document={terms} seo={SEO} />);
    expect(screen.getAllByRole('list').length).toBeGreaterThan(3);
    expect(screen.getAllByRole('link', { name: 'privacy@tabsira.me' }).length).toBeGreaterThan(0);
  });

  it('turns a web address into a link, the sentence full stop left outside', () => {
    const { sources } = legalMessages();
    render(<LegalPage document={sources} seo={{ ...SEO, path: '/sources' }} />);
    const quranpedia = screen.getByRole('link', { name: 'https://quranpedia.net' });
    expect(quranpedia).toHaveAttribute('href', 'https://quranpedia.net');
    expect(quranpedia).toHaveAttribute('dir', 'ltr');
    expect(
      screen.getByRole('link', { name: 'http://opendatacommons.org/licenses/odbl/1.0/' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'https://github.com/IslamWonder/tabsira' })
    ).toHaveAttribute('href', 'https://github.com/IslamWonder/tabsira');
  });

  it('uses no hover motion: nothing moves or scales on hover', () => {
    const { container } = render(<LegalPage document={terms} seo={SEO} />);
    expect(container.innerHTML).not.toMatch(/hover:(scale|translate|-translate|rotate)/);
  });
});
