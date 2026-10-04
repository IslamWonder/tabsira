import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SceneInsightList } from './scene-insight-list';
import { SceneIntro } from './scene-intro';
import { SceneStarter } from './scene-starter';

const POINTS = [
  { id: 'a', x: 0.2, y: 0.5, title: '[أولى]', glimpse: '[لمحة]', tone: 'gold' as const },
  { id: 'b', x: 0.5, y: 0.7, title: '[ثانية]', tone: 'emerald' as const },
];

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
    render(<SceneStarter onFile={onFile} className="extra" />);
    return { onFile, zone: screen.getByRole('region', { name: /اسحب صورة/ }) };
  }

  it('takes a photo from the file picker and from the camera', async () => {
    const { onFile, zone } = renderStarter();
    expect(zone).toHaveClass('extra');
    const photo = new File(['x'], 'scene.jpg', { type: 'image/jpeg' });
    await userEvent.upload(screen.getByLabelText('اختر صورة'), photo);
    // jsdom has no camera: the live camera falls back to the phone's camera picker.
    await userEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    const camera = await screen.findByLabelText(/التقط بالكاميرا/);
    expect(camera).toHaveAttribute('capture', 'environment');
    await userEvent.upload(camera, photo);
    expect(onFile).toHaveBeenCalledTimes(2);
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
});
