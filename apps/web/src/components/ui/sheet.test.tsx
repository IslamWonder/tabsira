import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Sheet } from './sheet';

function Harness({ onClose = () => undefined }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        افتح
      </button>
      <Sheet
        open={open}
        onClose={() => {
          onClose();
          setOpen(false);
        }}
        title="لماذا ظهر هذا؟"
        description="السبب والحدود"
      >
        <a href="#first">الأول</a>
        <button type="button">الأخير</button>
      </Sheet>
    </>
  );
}

async function openSheet(onClose?: () => void) {
  render(<Harness onClose={onClose} />);
  const opener = screen.getByRole('button', { name: 'افتح' });
  await userEvent.click(opener);
  return { opener, dialog: screen.getByRole('dialog', { name: 'لماذا ظهر هذا؟' }) };
}

describe('Sheet', () => {
  it('renders nothing while closed', () => {
    render(
      <Sheet open={false} onClose={vi.fn()} title="عنوان">
        محتوى
      </Sheet>
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens as a labelled modal dialog and moves focus into it', async () => {
    const { dialog } = await openSheet();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription('السبب والحدود');
    expect(screen.getByRole('button', { name: 'أغلق' })).toHaveFocus();
  });

  it('makes the page behind inert and stops it scrolling', async () => {
    await openSheet();
    const pageRoot = screen.getByRole('button', { name: 'افتح' }).closest('body > div');
    expect(pageRoot).toHaveAttribute('inert');
    expect(document.documentElement.style.overflow).toBe('hidden');
  });

  it('closes with Escape, gives focus back and releases the page', async () => {
    const onClose = vi.fn();
    const { opener } = await openSheet(onClose);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
    expect(opener.closest('body > div')).not.toHaveAttribute('inert');
    expect(document.documentElement.style.overflow).toBe('');
  });

  it('closes with the visible close button and with the backdrop', async () => {
    const onClose = vi.fn();
    await openSheet(onClose);
    await userEvent.click(screen.getByRole('button', { name: 'أغلق' }));
    await userEvent.click(screen.getByRole('button', { name: 'افتح' }));
    const backdrop = screen.getByRole('dialog').previousElementSibling as HTMLElement;
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('keeps Tab and Shift+Tab inside the sheet', async () => {
    const { dialog } = await openSheet();
    const close = screen.getByRole('button', { name: 'أغلق' });
    const first = screen.getByRole('link', { name: 'الأول' });
    const last = screen.getByRole('button', { name: 'الأخير' });

    await userEvent.tab({ shift: true });
    expect(last).toHaveFocus();
    await userEvent.tab();
    expect(close).toHaveFocus();
    await userEvent.tab();
    expect(first).toHaveFocus();

    act(() => dialog.focus());
    await userEvent.tab({ shift: true });
    expect(last).toHaveFocus();
  });

  it('ignores other keys', async () => {
    const { dialog } = await openSheet();
    const event = fireEvent.keyDown(dialog, { key: 'a' });
    expect(event).toBe(true);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('opens from an element that cannot take focus back, without failing', () => {
    const { rerender } = render(
      <>
        <svg role="img" aria-label="خريطة">
          <a href="#place">
            <circle r="4" />
          </a>
        </svg>
        <Sheet open={false} onClose={vi.fn()} title="عنوان">
          محتوى
        </Sheet>
      </>
    );
    // A link inside an SVG map is focusable but is not an HTMLElement.
    const svgLink = document.querySelector('svg a') as SVGAElement;
    act(() => svgLink.focus());
    expect(document.activeElement).toBe(svgLink);
    rerender(
      <>
        <svg role="img" aria-label="خريطة">
          <a href="#place">
            <circle r="4" />
          </a>
        </svg>
        <Sheet open onClose={vi.fn()} title="عنوان">
          محتوى
        </Sheet>
      </>
    );
    expect(screen.getByRole('button', { name: 'أغلق' })).toHaveFocus();
    expect(() =>
      rerender(
        <Sheet open={false} onClose={vi.fn()} title="عنوان">
          محتوى
        </Sheet>
      )
    ).not.toThrow();
  });

  it('can show the other theme for previews, and goes without a description', () => {
    render(
      <Sheet open onClose={vi.fn()} title="عنوان" theme="dark">
        محتوى
      </Sheet>
    );
    const dialog = screen.getByRole('dialog', { name: 'عنوان' });
    expect(dialog.parentElement).toHaveAttribute('data-theme', 'dark');
    expect(dialog).not.toHaveAttribute('aria-describedby');
  });
});
