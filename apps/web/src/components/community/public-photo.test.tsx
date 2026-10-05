import { render, screen } from '@testing-library/react';
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
});
