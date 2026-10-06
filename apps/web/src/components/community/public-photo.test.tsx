import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { PublicPhoto } from './public-photo';

describe('PublicPhoto', () => {
  it('renders a plain lazy image for an http(s) address, with the alt it is given', () => {
    render(<PublicPhoto url="https://media.tabsira.test/public/a.jpg" alt="[وصف]" />);
    const img = screen.getByRole('img', { name: '[وصف]' });
    expect(img).toHaveAttribute('src', 'https://media.tabsira.test/public/a.jpg');
    expect(img).toHaveAttribute('loading', 'lazy');
    expect(img).toHaveAttribute('decoding', 'async');
  });

  it('sends no referrer, so another host serving the photo never learns the page', () => {
    render(<PublicPhoto url="https://placepix.net/id/12/1080/1080" alt="[وصف]" />);
    expect(screen.getByRole('img', { name: '[وصف]' })).toHaveAttribute(
      'referrerpolicy',
      'no-referrer'
    );
  });

  it('shows the whole photo by default and crops a medium strip as a thumbnail', () => {
    const { unmount } = render(<PublicPhoto url="https://media.tabsira.test/a.jpg" alt="" />);
    expect(screen.getByTestId('public-photo')).toHaveClass('object-contain');
    unmount();
    render(<PublicPhoto url="https://media.tabsira.test/a.jpg" alt="" size="thumb" />);
    expect(screen.getByTestId('public-photo')).toHaveClass('object-cover');
  });

  it('leaves no broken frame behind when the photo fails to load', () => {
    const { container } = render(<PublicPhoto url="https://media.tabsira.test/gone.jpg" alt="" />);
    fireEvent.error(screen.getByTestId('public-photo'));
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing without an address, and nothing for one that is not http(s)', () => {
    for (const url of [
      null,
      'javascript:alert(1)',
      'data:image/jpeg;base64,AAAA',
      '/media/x.jpg',
    ]) {
      const { container, unmount } = render(<PublicPhoto url={url} alt="[وصف]" />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });

  it('opens the whole photo full screen on a tap, and closes on the button, Escape or a tap', async () => {
    render(<PublicPhoto url="https://media.tabsira.test/a.jpg" alt="[وصف]" />);
    const open = screen.getByRole('button', { name: 'اعرض بملء الشاشة: [وصف]' });
    expect(open).toHaveAttribute('aria-haspopup', 'dialog');
    await userEvent.click(open);
    const viewer = screen.getByRole('dialog', { name: '[وصف]' });
    expect(viewer.querySelector('img')).toHaveAttribute('src', 'https://media.tabsira.test/a.jpg');
    await userEvent.click(screen.getByRole('button', { name: 'أغلق' }));
    expect(screen.queryByRole('dialog')).toBeNull();

    await userEvent.click(open);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();

    await userEvent.click(open);
    const backdrop = screen.getByRole('dialog').previousElementSibling as HTMLElement;
    await userEvent.click(backdrop);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps a thumbnail a plain picture: its card links to the post instead', () => {
    render(<PublicPhoto url="https://media.tabsira.test/a.jpg" alt="" size="thumb" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
