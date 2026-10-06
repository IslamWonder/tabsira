// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SceneInsightList } from './scene-insight-list';

describe('SceneInsightList on the server', () => {
  it('renders the list, with no hint: the hint waits for a reader in a browser', () => {
    const html = renderToStaticMarkup(
      <SceneInsightList
        points={[{ id: 'a', x: 0.2, y: 0.5, title: '[أولى]' }]}
        onSelect={() => undefined}
        invite
      />
    );
    expect(html).toContain('[أولى]');
    expect(html).not.toContain('اختر بصيرة لتفتحها كاملة');
  });
});
