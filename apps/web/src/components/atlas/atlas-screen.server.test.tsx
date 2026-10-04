// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { AtlasScreen } from './atlas-screen';

vi.mock('next/navigation', () => ({ usePathname: () => '/atlas' }));

describe('AtlasScreen on the server', () => {
  it('renders the page with the default view, reading no address fragment', () => {
    const html = renderToStaticMarkup(<AtlasScreen />);
    expect(html).toContain('أطلس بصائر العالم');
    expect(html).not.toContain('maplibre');
  });
});
