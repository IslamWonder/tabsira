// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Sheet } from './sheet';

describe('Sheet on the server', () => {
  it('renders nothing, even when open, since there is no document to portal into', () => {
    expect(
      renderToStaticMarkup(
        <Sheet open onClose={() => undefined} title="عنوان">
          محتوى
        </Sheet>
      )
    ).toBe('');
  });
});
