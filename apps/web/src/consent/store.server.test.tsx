// @vitest-environment node
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { readConsent, type ServerConsent, useSeededConsent } from './store';

function Probe({ server }: { server: ServerConsent }) {
  return <p>{useSeededConsent(server).consent.status}</p>;
}

describe('the consent store on the server', () => {
  it('renders from the request and never seeds the module store shared by requests', () => {
    const html = renderToString(
      <Probe
        server={{
          consent: { status: 'asking', reason: 'first' },
          policy: null,
          view: 'summary',
          failed: false,
        }}
      />
    );
    expect(html).toContain('asking');
    expect(readConsent().consent.status).toBe('unknown');
  });
});
