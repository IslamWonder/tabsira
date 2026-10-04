import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { isImageFile, normaliseImageLink } from './image-link';
import { SceneInsightList } from './scene-insight-list';
import { SceneIntro } from './scene-intro';
import { SceneStarter } from './scene-starter';

const POINTS = [
  { id: 'a', x: 0.2, y: 0.5, title: '[أولى]', glimpse: '[لمحة]', tone: 'gold' as const },
  { id: 'b', x: 0.5, y: 0.7, title: '[ثانية]', tone: 'emerald' as const },
];

describe('normaliseImageLink and isImageFile', () => {
  it.each([
    ['  https://example.org/a.jpg ', 'https://example.org/a.jpg'],
    ['example.org/a.jpg', 'https://example.org/a.jpg'],
    ['//cdn.example.org/a.png', 'https://cdn.example.org/a.png'],
    ['http://example.org/a.webp', 'http://example.org/a.webp'],
  ])('accepts %s', (value, expected) => {
    expect(normaliseImageLink(value)).toBe(expected);
  });

  it.each([
    '',
    'not a link',
    'ftp://example.org/a.jpg',
    'https://localhost/a.jpg',
    'https://[',
    'javascript:alert(1)',
  ])('refuses %s', (value) => {
    expect(normaliseImageLink(value)).toBeNull();
  });

  it('tells images from other files', () => {
    expect(isImageFile(new File(['x'], 'a.jpg', { type: 'image/jpeg' }))).toBe(true);
    expect(isImageFile(new File(['x'], 'a.pdf', { type: 'application/pdf' }))).toBe(false);
  });
});

describe('SceneIntro and SceneInsightList', () => {
  it('give the gilded promise and the insights as a list', async () => {
    const onSelect = vi.fn();
    render(
      <>
        <SceneIntro chip={<span>[حالة]</span>} />
        <SceneInsightList points={POINTS} selectedId="b" onSelect={onSelect} />
      </>
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveClass('text-gilded');
    expect(screen.getByText('[حالة]')).toBeInTheDocument();
    const list = screen.getByRole('region', { name: 'المس البصيرة التي لفتتك' });
    const [first, second] = Array.from(list.querySelectorAll('button'));
    expect(second).toHaveAttribute('aria-current', 'true');
    expect(first).toHaveTextContent('[أولى] [لمحة]');
    await userEvent.click(first as HTMLButtonElement);
    expect(onSelect).toHaveBeenCalledWith('a');
  });

  it('go without a chip', () => {
    render(<SceneIntro />);
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });
});

describe('SceneStarter', () => {
  function renderStarter() {
    const onFile = vi.fn();
    const onLink = vi.fn();
    render(<SceneStarter onFile={onFile} onLink={onLink} className="extra" />);
    return { onFile, onLink, zone: screen.getByRole('region', { name: /اسحب صورة/ }) };
  }

  it('takes a photo from the file picker and from the camera', async () => {
    const { onFile, zone } = renderStarter();
    expect(zone).toHaveClass('extra');
    const photo = new File(['x'], 'scene.jpg', { type: 'image/jpeg' });
    await userEvent.upload(screen.getByLabelText('اختر صورة'), photo);
    await userEvent.upload(screen.getByLabelText(/التقط بالكاميرا/), photo);
    expect(onFile).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText(/التقط بالكاميرا/)).toHaveAttribute('capture', 'environment');
  });

  it('refuses a file that is not an image, plainly, and ignores a cancelled picker', () => {
    const { onFile } = renderStarter();
    const input = screen.getByLabelText('اختر صورة');
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'a.pdf', { type: 'application/pdf' })] },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('ليس صورة');
    fireEvent.change(input, { target: { files: [] } });
    expect(onFile).not.toHaveBeenCalled();
  });

  it('accepts a dropped photo and turns the circle while dragging', () => {
    const { onFile, zone } = renderStarter();
    fireEvent.dragOver(zone);
    expect(zone).toHaveTextContent('أفلت الصورة هنا');
    expect(zone.querySelector('[data-active="true"]')).not.toBeNull();
    fireEvent.dragLeave(zone);
    expect(zone).toHaveTextContent('اسحب صورة');
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(['x'], 'a.png', { type: 'image/png' })] },
    });
    fireEvent.drop(zone, { dataTransfer: { files: [] } });
    expect(onFile).toHaveBeenCalledOnce();
  });

  it('takes a pasted link, and says what is wrong with a bad one', async () => {
    const { onLink } = renderStarter();
    const toggle = screen.getByRole('button', { name: 'الصق رابط صورة' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const field = screen.getByLabelText('رابط الصورة');
    await userEvent.type(field, 'not a link');
    await userEvent.click(screen.getByRole('button', { name: 'استخدم الرابط' }));
    expect(screen.getByRole('alert')).toHaveTextContent('لا يبدو رابطًا');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    await userEvent.clear(field);
    await userEvent.type(field, 'example.org/rain.jpg');
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'استخدم الرابط' }));
    });
    expect(onLink).toHaveBeenCalledWith('https://example.org/rain.jpg');
    expect(screen.getByRole('alert')).toBeEmptyDOMElement();
  });
});
