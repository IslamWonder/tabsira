import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IDLE_MS } from '@/components/scene/use-idle-hint';
import { ScenePhoto, type ScenePoint } from './scene-photo';

const POINTS: ScenePoint[] = [
  { id: 'a', x: 0.3, y: 0.55, title: '[أولى]', glimpse: '[لمحة]' },
  { id: 'b', x: 0.7, y: 0.75, title: '[ثانية]', tone: 'emerald' },
  { id: 'outside', x: 1.4, y: 0.5, title: '[خارج الصورة]' },
];

function renderScene(points = POINTS, selectedId?: string) {
  const onSelect = vi.fn();
  render(
    <ScenePhoto
      src="/scene.jpg"
      alt="[وصف الصورة]"
      width={1200}
      height={1600}
      points={points}
      selectedId={selectedId}
      onSelect={onSelect}
      priority
      unoptimized
      className="h-96"
    >
      <p>[فوق الصورة]</p>
    </ScenePhoto>
  );
  return onSelect;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ScenePhoto', () => {
  it('shows the photo with its alt text and the overlay content', () => {
    renderScene();
    expect(screen.getByRole('img', { name: '[وصف الصورة]' })).toHaveAttribute('src', '/scene.jpg');
    expect(screen.getByText('[فوق الصورة]')).toBeInTheDocument();
  });

  it('draws a button per valid point and drops points outside the photo', () => {
    renderScene();
    const drawn = document.querySelectorAll('[data-point-id]');
    expect(Array.from(drawn).map((element) => element.getAttribute('data-point-id'))).toEqual([
      'a',
      'b',
    ]);
  });

  it('lists the same points with their place in words, selecting the same ids', async () => {
    const onSelect = renderScene(POINTS, 'b');
    const list = screen.getByRole('navigation', { name: 'البصائر في الصورة' });
    const items = within(list).getAllByRole('button');
    expect(items.map((item) => item.textContent)).toEqual([
      '[أولى] [لمحة]، يسار وسط الصورة',
      '[ثانية] أسفل يمين الصورة',
    ]);
    expect(items[1]).toHaveAttribute('aria-current', 'true');
    await userEvent.click(items[0] as HTMLElement);
    await userEvent.click(document.querySelector('[data-point-id="b"]') as HTMLElement);
    expect(onSelect.mock.calls).toEqual([['a'], ['b']]);
  });

  it('moves the points through the crop once the box is measured, and follows resizes', () => {
    const observers: Array<{ callback: () => void; disconnect: ReturnType<typeof vi.fn> }> = [];
    vi.stubGlobal(
      'ResizeObserver',
      class {
        disconnect = vi.fn();
        constructor(callback: () => void) {
          observers.push({ callback, disconnect: this.disconnect });
        }
        observe() {}
      }
    );
    const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(400);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(800);

    renderScene([{ id: 'edge', x: 0.12, y: 0.5, title: '[قرب الحافة]' }]);
    // 3:4 photo in a 1:2 box: x = 0.12 falls in the cropped side.
    expect(document.querySelector('[data-point-id]')).toBeNull();

    width.mockReturnValue(1200);
    act(() => observers[0]?.callback());
    expect(document.querySelector('[data-point-id="edge"]')).not.toBeNull();
  });

  it('works where ResizeObserver does not exist', () => {
    vi.stubGlobal('ResizeObserver', undefined);
    renderScene();
    expect(document.querySelectorAll('[data-point-id]')).toHaveLength(2);
  });
});

describe('ScenePhoto: the call to choose', () => {
  const sheens = () => Array.from(document.querySelectorAll('[data-point-id] .fx-sheen'));

  it('runs a light over each label when asked, again after a stillness, and not for the chosen one', () => {
    vi.useFakeTimers();
    render(
      <ScenePhoto
        src="/scene.jpg"
        alt="[وصف الصورة]"
        width={1200}
        height={1600}
        points={POINTS}
        selectedId="b"
        onSelect={vi.fn()}
        invite
      />
    );
    const first = sheens();
    expect(first).toHaveLength(1);
    expect(first[0]?.closest('[data-point-id]')).toHaveAttribute('data-point-id', 'a');
    act(() => vi.advanceTimersByTime(IDLE_MS));
    // A new element: the animation plays again rather than being skipped.
    expect(sheens()[0]).not.toBe(first[0]);
    vi.useRealTimers();
  });

  it('stays quiet when not asked', () => {
    renderScene();
    expect(sheens()).toHaveLength(0);
  });
});
