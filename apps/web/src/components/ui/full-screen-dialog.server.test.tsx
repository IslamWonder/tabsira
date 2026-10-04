// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FullScreenDialog } from './full-screen-dialog';

describe('FullScreenDialog on the server', () => {
  it('is in the HTML already open, over the wash, so the first paint shows it', () => {
    const html = renderToStaticMarkup(
      <FullScreenDialog open labelledBy="t">
        <h2 id="t">[عنوان]</h2>
      </FullScreenDialog>
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('fx-scrim');
    expect(html).toContain('[عنوان]');
  });
});
