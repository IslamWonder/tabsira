import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { CONTRAST, LINKS, TEXT_SIZE } from '@/preferences/accessibility';
import { ReadingAids } from './reading-aids';

const root = document.documentElement;

afterEach(() => {
  for (const name of ['data-text-size', 'data-contrast', 'data-links']) {
    root.removeAttribute(name);
  }
});

describe('ReadingAids', () => {
  it('chooses the text size as one of three, applied at once', async () => {
    render(<ReadingAids />);
    expect(screen.getByRole('heading', { name: 'سهولة القراءة' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'عادي' })).toBeChecked();
    await userEvent.click(screen.getByRole('radio', { name: 'أكبر' }));
    expect(screen.getByRole('radio', { name: 'أكبر' })).toBeChecked();
    expect(root.dataset.textSize).toBe('larger');
    expect(window.localStorage.getItem(TEXT_SIZE.key)).toBe('larger');
  });

  it('switches a stronger contrast and underlined links on and off', async () => {
    render(<ReadingAids />);
    const contrast = screen.getByRole('switch', { name: 'تباين أعلى' });
    const links = screen.getByRole('switch', { name: 'تمييز الروابط' });
    expect(contrast).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(contrast);
    await userEvent.click(links);
    expect(contrast).toHaveAttribute('aria-checked', 'true');
    expect(root.dataset.contrast).toBe('more');
    expect(window.localStorage.getItem(LINKS.key)).toBe('underline');
    await userEvent.click(contrast);
    await userEvent.click(links);
    expect(root.hasAttribute('data-contrast')).toBe(false);
    expect(window.localStorage.getItem(CONTRAST.key)).toBeNull();
    expect(root.hasAttribute('data-links')).toBe(false);
  });
});
