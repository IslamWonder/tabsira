// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ThemeSwitcher } from './theme-switcher';

describe('ThemeSwitcher on the server', () => {
  it('renders the automatic choice, since only the device knows the stored one', () => {
    const html = renderToStaticMarkup(<ThemeSwitcher />);
    expect(html).toMatch(/checked="" value="system"/);
    expect(html).not.toMatch(/checked="" value="dark"/);
  });
});
