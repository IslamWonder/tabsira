import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { BURST_EVENT } from '@/components/fx/burst';
import { VICTORY_EVENT } from '@/components/fx/celebrate';
import { DoneButton } from './done-button';
import { EvidencePair } from './evidence-pair';
import {
  ExplanationBlock,
  InsightActions,
  InsightHeader,
  InsightPhoto,
  InsightTools,
  SeenNote,
} from './insight-frame';

describe('InsightPhoto', () => {
  it('shows the photo, the way back for phones, and the caption for the desktop', () => {
    render(
      <InsightPhoto src="/p.jpg" alt="[صورة]" width={1200} height={1600} backHref="/" unoptimized />
    );
    expect(screen.getByRole('img', { name: '[صورة]' })).toBeInTheDocument();
    const back = screen.getByRole('link', { name: 'العودة إلى المشهد' });
    expect(back).toHaveClass('desktop:hidden');
    expect(screen.getByText('تبقى الصورة أمامك وأنت تقرأ.')).toBeInTheDocument();
  });

  it('highlights the point the insight is about, and nothing outside the photo', () => {
    const { container, rerender } = render(
      <InsightPhoto
        src="/p.jpg"
        alt="[صورة]"
        width={1200}
        height={1600}
        backHref="/"
        focus={{ x: 0.3, y: 0.5, title: '[نقطة]' }}
      />
    );
    const marker = container.querySelector(
      'figure span[aria-hidden="true"][style*="left"]'
    ) as HTMLElement;
    expect(marker.style.left).toBe('30%');
    expect(screen.getByText('[نقطة]')).toBeInTheDocument();
    rerender(
      <InsightPhoto
        src="/p.jpg"
        alt="[صورة]"
        width={1200}
        height={1600}
        backHref="/"
        focus={{ x: 2, y: 0.5, title: '[نقطة]' }}
      />
    );
    expect(screen.queryByText('[نقطة]')).toBeNull();
  });

  it('drops a point the crop hides', () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(400);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(800);
    render(
      <InsightPhoto
        src="/p.jpg"
        alt="[صورة]"
        width={1200}
        height={1600}
        backHref="/"
        focus={{ x: 0.05, y: 0.5, title: '[نقطة]' }}
      />
    );
    expect(screen.queryByText('[نقطة]')).toBeNull();
  });
});

describe('InsightHeader, SeenNote, ExplanationBlock', () => {
  it('give the title, the glimpse, what was seen and the labelled explanation', () => {
    render(
      <>
        <InsightHeader backHref="/" chips={<span>[وسم]</span>} title="[عنوان]" glimpse="[لمحة]" />
        <SeenNote text="[ما ظهر]" />
        <ExplanationBlock text="[شرح]" />
      </>
    );
    expect(screen.getByRole('heading', { level: 1, name: '[عنوان]' })).toHaveClass('text-gilded');
    expect(screen.getByRole('link', { name: 'العودة إلى المشهد' })).toHaveClass(
      'desktop:inline-flex'
    );
    expect(screen.getByText('[وسم]')).toBeInTheDocument();
    expect(screen.getByText('ما ظهر في الصورة:').parentElement).toHaveTextContent('[ما ظهر]');
    const explanation = screen.getByRole('region', { name: 'شرح تبصرة' });
    expect(explanation).toHaveTextContent('[شرح]');
  });

  it('go without chips', () => {
    const { container } = render(<InsightHeader backHref="/" title="[عنوان]" glimpse="[لمحة]" />);
    expect(container.querySelectorAll('header > div')).toHaveLength(0);
  });
});

describe('InsightTools and InsightActions', () => {
  it('open the reason and the chat, finish and share', async () => {
    const onWhy = vi.fn();
    const onDiscuss = vi.fn();
    const onDone = vi.fn();
    const onShare = vi.fn();
    render(
      <>
        <InsightTools onWhy={onWhy} onDiscuss={onDiscuss} />
        <InsightActions onDone={onDone} onShare={onShare} />
      </>
    );
    await userEvent.click(screen.getByRole('button', { name: 'لماذا ظهر هذا؟' }));
    await userEvent.click(screen.getByRole('button', { name: /ناقش البصيرة/ }));
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    await userEvent.click(screen.getByRole('button', { name: 'شارك' }));
    expect([onWhy, onDiscuss, onDone, onShare].map((fn) => fn.mock.calls.length)).toEqual([
      1, 1, 1, 1,
    ]);
  });
});

describe('DoneButton', () => {
  it('celebrates once the save has succeeded, not on the tap', async () => {
    const bursts = vi.fn();
    const victories = vi.fn();
    window.addEventListener(BURST_EVENT, bursts);
    window.addEventListener(VICTORY_EVENT, victories);
    const onDone = vi.fn();
    const { rerender } = render(<DoneButton onDone={onDone} />);
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    expect(onDone).toHaveBeenCalledOnce();
    expect(bursts).not.toHaveBeenCalled();

    rerender(<DoneButton status="saving" onDone={onDone} />);
    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');

    act(() => rerender(<DoneButton status="done" onDone={onDone} />));
    expect(bursts).toHaveBeenCalledOnce();
    expect(victories).toHaveBeenCalledOnce();
    rerender(<DoneButton status="done" onDone={onDone} className="extra" />);
    expect(bursts).toHaveBeenCalledOnce();
    expect(screen.getByRole('button')).toHaveClass('extra');
    window.removeEventListener(BURST_EVENT, bursts);
    window.removeEventListener(VICTORY_EVENT, victories);
  });
});

describe('EvidencePair', () => {
  it('brings the Quran in from the start, the Sunnah from the end, with a thread between', () => {
    const { container } = render(<EvidencePair quran={<p>[قرآن]</p>} sunnah={<p>[سنة]</p>} />);
    const [quran, thread, sunnah] = Array.from(container.firstElementChild?.children ?? []);
    expect(quran?.className).toContain('fx-from-start');
    expect(thread?.tagName.toLowerCase()).toBe('svg');
    expect(sunnah?.className).toContain('fx-from-end');
    expect(within(sunnah as HTMLElement).getByText('[سنة]')).toBeInTheDocument();
  });

  it('stands the Quran alone without a hadith, and may sit side by side on wide screens', () => {
    const { container, rerender } = render(<EvidencePair quran={<p>[قرآن]</p>} />);
    expect(container.querySelector('svg')).toBeNull();
    rerender(<EvidencePair quran={<p>[قرآن]</p>} sunnah={<p>[سنة]</p>} sideBySide />);
    expect(container.firstElementChild).toHaveClass('wide:grid');
  });
});
