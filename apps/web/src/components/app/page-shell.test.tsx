import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ServerConsent } from '@/consent/store';
import { openConsentSettings } from '@/consent/store';
import { RECORD } from '@/test/fixtures';
import { PageShell } from './page-shell';

const OPEN: ServerConsent = {
  consent: { status: 'asking', reason: 'first' },
  policy: null,
  view: 'summary',
  failed: false,
};
const CLOSED: ServerConsent = { ...OPEN, consent: { status: 'decided', record: RECORD } };

describe('PageShell', () => {
  it('is inert and hidden under an open cookie choice, from the server HTML on', () => {
    const html = renderToString(
      <PageShell consent={OPEN}>
        <a href="/world">[رابط]</a>
      </PageShell>
    );
    expect(html).toContain('inert=""');
    expect(html).toContain('aria-hidden="true"');
  });

  it('is the ordinary page once a choice holds, and inert again while it is reopened', () => {
    render(
      <PageShell consent={CLOSED}>
        <a href="/world">[رابط]</a>
      </PageShell>
    );
    const shell = screen.getByRole('link').parentElement as HTMLElement;
    expect(shell).not.toHaveAttribute('inert');
    expect(shell).not.toHaveAttribute('aria-hidden');
    act(() => openConsentSettings());
    expect(shell).toHaveAttribute('inert');
  });
});
