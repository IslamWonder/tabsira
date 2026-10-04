import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FullScreenDialog } from './full-screen-dialog';

describe('FullScreenDialog', () => {
  it('holds focus on itself when it has no control, and covers the page', () => {
    render(
      <FullScreenDialog open labelledBy="title" layer="z-[65]">
        <h2 id="title">[عنوان]</h2>
      </FullScreenDialog>
    );
    const dialog = screen.getByRole('dialog', { name: '[عنوان]' });
    expect(dialog).toHaveFocus();
    const tab = fireEvent.keyDown(document, { key: 'Tab' });
    expect(tab).toBe(false);
    expect(dialog).toHaveFocus();
    expect(dialog.closest('.fixed')).toHaveClass('z-[65]');
  });

  it('renders nothing while closed', () => {
    render(
      <FullScreenDialog open={false} labelledBy="title">
        <h2 id="title">[عنوان]</h2>
      </FullScreenDialog>
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
