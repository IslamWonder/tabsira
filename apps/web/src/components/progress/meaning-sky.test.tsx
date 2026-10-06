import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import type { Progress } from '@/progress/api';
import { PROGRESS, PROGRESS_REFERENCE } from '@/test/world';
import { MeaningSkyScene, SKY_TALL_SRC, SKY_WIDE_SRC, type SkyState } from './meaning-sky';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  usePathname: () => '/me/practice',
}));

const M = messages.practiceView.sky;

function scene(state: SkyState) {
  return render(
    <CaptureProvider>
      <MeaningSkyScene state={state} />
    </CaptureProvider>
  );
}

const ready = (sky: Progress['sky'] = PROGRESS.sky): SkyState => ({ status: 'ready', sky });

const stars = () =>
  screen
    .queryAllByRole('button', { pressed: undefined })
    .filter((button) => button.classList.contains('sky-star'));

afterEach(() => {
  vi.restoreAllMocks();
});

describe('the scene around the stars', () => {
  it('lays its heading over a picture that is decoration only', () => {
    const { container } = scene(ready());
    expect(screen.getByRole('heading', { level: 2, name: M.title })).toBeInTheDocument();
    expect(screen.getByText(M.lead)).toBeInTheDocument();
    const picture = container.querySelector('picture');
    expect(picture?.parentElement).toHaveAttribute('aria-hidden', 'true');
    expect(picture?.parentElement?.className).toContain('pointer-events-none');
    expect(picture?.querySelector('img')).toHaveAttribute('alt', '');
    // The head of the page loads at once, at the size of the screen whichever cut is used.
    expect(picture?.querySelector('img')).toHaveAttribute('loading', 'eager');
    expect(picture?.querySelector('img')).toHaveAttribute('fetchpriority', 'high');
    expect(picture?.querySelector('source')).toHaveAttribute('sizes', '100vw');
    expect(picture?.querySelector('source')?.getAttribute('srcset')).toContain(
      encodeURIComponent(SKY_WIDE_SRC)
    );
    expect(picture?.querySelector('img')?.getAttribute('srcset')).toContain(
      encodeURIComponent(SKY_TALL_SRC)
    );
  });

  it('says it is loading with no star and no count, never a misleading zero', () => {
    scene({ status: 'loading' });
    expect(screen.getByRole('status')).toHaveTextContent(M.loading);
    expect(stars()).toHaveLength(0);
    expect(screen.queryByText(M.count(0))).toBeNull();
    // Not busy: a busy region may keep its own status line from being read.
    expect(screen.getByRole('region', { name: M.title })).toHaveAttribute('aria-busy', 'false');
  });

  it('tells a failure apart from an empty sky and offers to try again', async () => {
    const retry = vi.fn();
    scene({ status: 'failed', retry });
    expect(screen.getByRole('alert')).toHaveTextContent(M.unavailable);
    expect(screen.queryByText(M.emptyTitle)).toBeNull();
    expect(stars()).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: messages.practiceView.retry }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it('invites a first scene while nothing was learned, and opens the camera', async () => {
    scene(ready({ count: 0, stars: [] }));
    expect(screen.getByText(M.emptyTitle)).toBeInTheDocument();
    expect(screen.getByText(M.empty)).toBeInTheDocument();
    expect(screen.getByText(M.note)).toBeInTheDocument();
    expect(stars()).toHaveLength(0);
    expect(screen.queryByText(M.chosen)).toBeNull();
    expect(screen.queryByText(M.count(0))).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: M.cta }));
    expect(await screen.findByRole('dialog', { name: 'صوّر مشهدًا' })).toBeInTheDocument();
  });

  it('marks itself busy while a reload runs, keeping what it shows', () => {
    scene({ status: 'ready', sky: PROGRESS.sky, refreshing: true });
    expect(screen.getByRole('region', { name: M.title })).toHaveAttribute('aria-busy', 'true');
    expect(stars()).toHaveLength(2);
  });
});

describe('the stars', () => {
  it('draws one named button per meaning, in a group that says what they are', () => {
    scene(ready());
    const group = screen.getByRole('group', { name: M.label });
    expect(
      within(group).getByRole('button', { name: '[معنى أول]، بصيرة واحدة مرتبطة' })
    ).toBeVisible();
    expect(
      within(group).getByRole('button', { name: '[معنى ثان]، بصيرتان مرتبطتان' })
    ).toBeVisible();
    expect(group).toHaveTextContent('[معنى أول]');
    expect(screen.getByText(M.count(2))).toBeInTheDocument();
  });

  it('chooses the meaning learned last until the learner chooses another', () => {
    scene(ready());
    const latest = screen.getByRole('button', { name: /^\[معنى ثان\]/ });
    expect(latest).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /^\[معنى أول\]/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(document.querySelector('.sky-dock strong')).toHaveTextContent('[معنى ثان]');
    expect(latest.getAttribute('aria-controls')).toBe(document.querySelector('.sky-dock')?.id);
  });

  it('shows the chosen meaning in the dock and announces it, and a second press keeps it', async () => {
    scene(ready());
    const live = document.querySelector('[aria-live="polite"]');
    expect(live).toHaveTextContent('');
    const first = screen.getByRole('button', { name: /^\[معنى أول\]/ });
    await userEvent.click(first);
    expect(first).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelector('.sky-dock')).toHaveTextContent('[معنى أول]');
    expect(document.querySelector('.sky-dock')).toHaveTextContent('بصيرة واحدة مرتبطة');
    expect(live).toHaveTextContent('[معنى أول]، بصيرة واحدة مرتبطة');
    await userEvent.click(first);
    expect(first).toHaveAttribute('aria-pressed', 'true');
  });

  it('is chosen from the keyboard with Enter and Space', async () => {
    scene(ready());
    const first = screen.getByRole('button', { name: /^\[معنى أول\]/ });
    first.focus();
    await userEvent.keyboard('{Enter}');
    expect(first).toHaveAttribute('aria-pressed', 'true');
    const second = screen.getByRole('button', { name: /^\[معنى ثان\]/ });
    second.focus();
    await userEvent.keyboard(' ');
    expect(second).toHaveAttribute('aria-pressed', 'true');
  });

  it('places a star from the place its name gives, in pixels of its field', () => {
    scene(ready());
    const star = screen.getByRole('button', { name: /^\[معنى أول\]/ });
    // The field cannot be measured here; its nominal size is 1000 × 500.
    expect(star.style.left).toBe('200px');
    expect(star.style.top).toBe('128px');
  });

  it('lights a meaning learned since the scene opened, once, and no other', () => {
    const { rerender } = scene(ready());
    expect(document.querySelector('[data-new]')).toBeNull();
    const extra = {
      concept: '[معنى ثالث]',
      count: 1,
      first_seen: '2026-10-04T08:00:00Z',
      x: 0.5,
      y: 0.2,
      insights: [{ id: '104', title: '[بصيرة رابعة]', completed_at: '2026-10-04T08:00:00Z' }],
    };
    rerender(
      <CaptureProvider>
        <MeaningSkyScene state={ready({ count: 3, stars: [...PROGRESS.sky.stars, extra] })} />
      </CaptureProvider>
    );
    const lit = Array.from(document.querySelectorAll('[data-new="true"]'));
    expect(lit.map((element) => element.textContent)).toEqual(['[معنى ثالث]']);
  });
});

describe('the dock', () => {
  it('says when the meaning first appeared, from the record and nothing else', () => {
    scene(ready());
    expect(document.querySelector('.sky-dock')).toHaveTextContent(
      M.about(formatDay('2026-10-02T08:00:00Z'))
    );
  });

  it('opens the only insight of a meaning directly', async () => {
    scene(ready());
    await userEvent.click(screen.getByRole('button', { name: /^\[معنى أول\]/ }));
    expect(screen.getByRole('link', { name: M.openOne })).toHaveAttribute('href', '/insight/101');
  });

  it('lists the insights of a meaning in a panel, each opening its own page', async () => {
    scene(ready());
    await userEvent.click(screen.getByRole('button', { name: M.open }));
    const panel = await screen.findByRole('dialog', { name: M.panelTitle('[معنى ثان]') });
    const links = within(panel).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/insight/102',
      '/insight/103',
    ]);
    expect(links[0]).toHaveTextContent('[بصيرة ثانية]');
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('offers no way to open insights the record does not list', () => {
    const [first] = PROGRESS.sky.stars;
    scene(
      ready({ count: 1, stars: [{ ...(first as Progress['sky']['stars'][number]), insights: [] }] })
    );
    expect(screen.queryByRole('link', { name: M.openOne })).toBeNull();
    expect(screen.queryByRole('button', { name: M.open })).toBeNull();
  });
});

describe('a sky too full to draw every star', () => {
  it('keeps every meaning within reach through the list of all meanings', async () => {
    // Every star as wide as half the field: only a few fit, the rest stay in the list.
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(600);
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(300);
    scene(ready(PROGRESS_REFERENCE.sky));
    const all = screen.getByRole('button', { name: M.all(8) });
    const hidden = stars().filter((button) => button.classList.contains('invisible'));
    expect(hidden.length).toBeGreaterThan(0);
    expect(hidden.every((button) => button.tabIndex === -1)).toBe(true);
    await userEvent.click(all);
    const panel = await screen.findByRole('dialog', { name: M.allTitle });
    const items = within(panel)
      .getAllByRole('button')
      .filter((button) => button.textContent?.includes('مرتبط'));
    expect(items).toHaveLength(8);
    await userEvent.click(within(panel).getByRole('button', { name: /^التفكر/ }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.querySelector('.sky-dock strong')).toHaveTextContent('التفكر');
  });

  it('shows no list button while every star fits', () => {
    scene(ready(PROGRESS_REFERENCE.sky));
    expect(screen.queryByRole('button', { name: M.all(8) })).toBeNull();
  });
});

describe('measuring the sky', () => {
  function rect(left: number, top: number, width: number, height: number): DOMRect {
    return {
      left,
      top,
      width,
      height,
      right: left + width,
      bottom: top + height,
      x: left,
      y: top,
      toJSON: () => ({}),
    } as DOMRect;
  }

  it('keeps the stars clear of the heading it measures in a real field', () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement
    ) {
      if (this.tagName === 'FIELDSET') {
        return rect(100, 100, 800, 400);
      }
      // The heading block: the field's whole top right corner.
      if (this.querySelector('#practice-sky')) {
        return rect(500, 0, 400, 300);
      }
      return rect(0, 0, 0, 0);
    });
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(80);
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(70);
    const star = { ...(PROGRESS.sky.stars[0] as Progress['sky']['stars'][number]), x: 0.8, y: 0.1 };
    scene(ready({ count: 1, stars: [star] }));
    const button = screen.getByRole('button', { name: /^\[معنى أول\]/ });
    const left = Number.parseFloat(button.style.left);
    const top = Number.parseFloat(button.style.top);
    // Field pixels: the heading covers x ≥ 400 down to y = 200; the star sits left of it or below it.
    expect(left + 40 <= 400 || top >= 200).toBe(true);
  });

  it('lays the stars out again once the font is in, and when the field, heading or dock changes size', async () => {
    let resized: () => void = () => undefined;
    const disconnect = vi.fn();
    const watched: Element[] = [];
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resized = callback;
        }
        observe(element: Element) {
          watched.push(element);
        }
        disconnect = disconnect;
      }
    );
    let ready_: () => void = () => undefined;
    const fonts = {
      ready: new Promise<void>((resolve) => {
        ready_ = resolve;
      }),
    };
    Object.defineProperty(document, 'fonts', { value: fonts, configurable: true });
    const width = vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(0);
    const { unmount } = scene(ready());
    const star = screen.getByRole('button', { name: /^\[معنى أول\]/ });
    expect(star.style.left).toBe('200px');
    expect(watched).toContain(document.querySelector('fieldset'));
    expect(watched).toContain(document.querySelector('.sky-dock'));
    expect(watched).toContain(screen.getByRole('heading', { level: 2 }).parentElement);
    // The font arrived: names are measured again (here wider), the stars stay where they fit.
    width.mockReturnValue(120);
    await act(async () => {
      ready_();
      await fonts.ready;
    });
    act(() => resized());
    expect(star.style.left).toBe('200px');
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
    Reflect.deleteProperty(document, 'fonts');
    vi.unstubAllGlobals();
  });

  it('ignores a font that arrives after the scene is gone', async () => {
    const fonts = { ready: Promise.resolve() };
    Object.defineProperty(document, 'fonts', { value: fonts, configurable: true });
    const { unmount } = scene(ready());
    unmount();
    await act(async () => {
      await fonts.ready;
    });
    expect(document.querySelector('.sky-star')).toBeNull();
    Reflect.deleteProperty(document, 'fonts');
  });

  it('lights nothing when a reload brings back the same meanings', () => {
    const { rerender } = scene(ready());
    rerender(
      <CaptureProvider>
        <MeaningSkyScene state={ready({ ...PROGRESS.sky, stars: [...PROGRESS.sky.stars] })} />
      </CaptureProvider>
    );
    expect(document.querySelector('[data-new]')).toBeNull();
  });

  it('orders meanings first met at the same moment by name, so the layout never depends on the answer order', () => {
    const [first, second] = PROGRESS.sky.stars as [
      Progress['sky']['stars'][number],
      Progress['sky']['stars'][number],
    ];
    const same = { ...second, first_seen: first.first_seen };
    scene(ready({ count: 2, stars: [same, first] }));
    // The later name in that order is the one chosen by default.
    expect(screen.getByRole('button', { name: /^\[معنى ثان\]/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('closes the list of all meanings with Escape, choosing nothing', async () => {
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(600);
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(300);
    scene(ready(PROGRESS_REFERENCE.sky));
    await userEvent.click(screen.getByRole('button', { name: M.all(8) }));
    await screen.findByRole('dialog', { name: M.allTitle });
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.querySelector('.sky-dock strong')).toHaveTextContent('الرحمة');
  });
});

describe('the count of insights', () => {
  it('agrees with the number in Arabic', () => {
    expect([1, 2, 3, 10, 11, 25].map(M.linked)).toEqual([
      'بصيرة واحدة مرتبطة',
      'بصيرتان مرتبطتان',
      '3 بصائر مرتبطة',
      '10 بصائر مرتبطة',
      '11 بصيرة مرتبطة',
      '25 بصيرة مرتبطة',
    ]);
  });
});
