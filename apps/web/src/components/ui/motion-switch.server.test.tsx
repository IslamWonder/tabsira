// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MotionSwitch } from './motion-switch';

describe('MotionSwitch on the server', () => {
  it('renders on, since only the device knows the stored choice', () => {
    expect(renderToStaticMarkup(<MotionSwitch />)).toContain('aria-checked="true"');
  });
});
