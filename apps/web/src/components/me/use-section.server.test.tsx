// @vitest-environment node
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { useOpenSection } from './use-section';

function Probe() {
  const { open } = useOpenSection(['account', 'data']);
  return <p>{open ?? 'none'}</p>;
}

describe('useOpenSection on the server', () => {
  it('opens nothing: the address hash never reaches the server', () => {
    expect(renderToString(<Probe />)).toContain('none');
  });
});
