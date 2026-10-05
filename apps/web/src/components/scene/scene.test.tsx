import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CaptureCard } from './capture-card';
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
    return { onFile, zone: screen.getByRole('region', { name: 'صوّر مشهدك أنت' }) };
  }

  it('takes a photo from the file picker and from the camera', async () => {
    const { onFile, zone } = renderStarter();
    expect(zone).toHaveClass('extra');
    const photo = new File(['x'], 'scene.jpg', { type: 'image/jpeg' });
    await userEvent.upload(screen.getByLabelText('اختر صورة'), photo);
    // jsdom has no camera, which the starter sees at once: the phone's camera picker shows.
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

  it('accepts a dropped photo and marks itself while dragging', () => {
    const { onFile, zone } = renderStarter();
    fireEvent.dragOver(zone);
    expect(zone).toHaveTextContent('أفلت الصورة هنا');
    expect(zone).toHaveClass('outline-[var(--focus)]');
    fireEvent.dragLeave(zone);
    expect(zone).toHaveTextContent('اسحب صورة');
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(['x'], 'a.png', { type: 'image/png' })] },
    });
    fireEvent.drop(zone, { dataTransfer: { files: [] } });
    expect(onFile).toHaveBeenCalledOnce();
  });
});

describe('CaptureCard', () => {
  function renderCard() {
    const onFile = vi.fn();
    const onCamera = vi.fn();
    render(<CaptureCard onFile={onFile} onCamera={onCamera} className="extra" />);
    return { onFile, onCamera, card: screen.getByRole('region', { name: 'صوّر مشهدك أنت' }) };
  }

  it('opens the camera with its one glowing call, and takes a photo from the gallery', async () => {
    const { onFile, onCamera, card } = renderCard();
    expect(card).toHaveClass('extra');
    // Said before anything leaves the device.
    expect(card).toHaveTextContent('تُرسل صورتك إلى مزوّد الذكاء الاصطناعي');
    const camera = screen.getByRole('button', { name: 'التقط صورة' });
    expect(camera).toHaveAttribute('aria-haspopup', 'dialog');
    await userEvent.click(camera);
    expect(onCamera).toHaveBeenCalledOnce();
    await userEvent.upload(
      screen.getByLabelText('اختر صورة'),
      new File(['x'], 'scene.jpg', { type: 'image/jpeg' })
    );
    expect(onFile).toHaveBeenCalledOnce();
  });

  it('refuses a file that is not an image, and takes a dropped photo', () => {
    const { onFile, card } = renderCard();
    fireEvent.change(screen.getByLabelText('اختر صورة'), {
      target: { files: [new File(['x'], 'a.pdf', { type: 'application/pdf' })] },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('ليس صورة');
    fireEvent.dragOver(card);
    expect(card).toHaveTextContent('أفلت الصورة هنا');
    fireEvent.drop(card, {
      dataTransfer: { files: [new File(['x'], 'a.png', { type: 'image/png' })] },
    });
    expect(card).toHaveTextContent('اسحب صورة');
    expect(onFile).toHaveBeenCalledOnce();
    expect(screen.getByRole('alert')).toBeEmptyDOMElement();
  });
});
