import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { CommunitySummary as Summary } from '@/lib/community-summary';
import { CommunitySummary } from './community-summary';

const FULL: Summary = {
  members: 1024,
  insights: 3170,
  reactions: 9000,
  atlas_entries: 860,
  countries: 22,
  sponsorships_open: 41,
};

function card(summary: Partial<Summary> = {}) {
  render(<CommunitySummary summary={{ ...FULL, ...summary }} />);
  return screen.getByRole('region', { name: 'مجتمع تبصرة' });
}

/** Each figure as a reader hears it: the label, then the value and its note. */
function figures(region: HTMLElement): string[] {
  return Array.from(region.querySelectorAll('dl > div'), (item) =>
    Array.from(item.children, (child) => child.textContent).join(' ')
  );
}

describe('CommunitySummary', () => {
  it('reads each public count as text, in Arabic-Indic digits, with one way onward', () => {
    const region = card();

    expect(figures(region)).toEqual([
      'الأعضاء ١٬٠٢٤ من ٢٢ بلدًا',
      'بصائر منشورة ٣٬١٧٠',
      'على الأطلس ٨٦٠',
      'تنتظر الكفالة ٤١',
    ]);
    const links = within(region).getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/community');
    expect(links[0]).toHaveTextContent('تعرّف إلى المجتمع');
  });

  it('leaves out what is switched off, and leads to the atlas without the network', () => {
    const region = card({ insights: null, reactions: null, sponsorships_open: null });

    expect(figures(region)).toEqual(['الأعضاء ١٬٠٢٤ من ٢٢ بلدًا', 'على الأطلس ٨٦٠']);
    expect(within(region).getByRole('link', { name: 'افتح الأطلس' })).toHaveAttribute(
      'href',
      '/atlas'
    );
  });

  it('has no link and no country line when only the members are known', () => {
    const region = card({
      insights: null,
      reactions: null,
      atlas_entries: null,
      countries: null,
      sponsorships_open: null,
    });

    expect(figures(region)).toEqual(['الأعضاء ١٬٠٢٤']);
    expect(within(region).queryByRole('link')).toBeNull();
  });

  it('shows no sponsorship figure while nothing waits for one', () => {
    const shown = figures(card({ sponsorships_open: 0 }));
    expect(shown).toHaveLength(3);
    expect(shown.join()).not.toContain('تنتظر الكفالة');
  });

  it.each([
    [1, 'من بلد واحد'],
    [2, 'من بلدين'],
    [7, 'من ٧ بلدان'],
    [11, 'من ١١ بلدًا'],
  ])('says %i countries in correct Arabic', (countries, note) => {
    expect(figures(card({ countries }))[0]).toBe(`الأعضاء ١٬٠٢٤ ${note}`);
  });
});
