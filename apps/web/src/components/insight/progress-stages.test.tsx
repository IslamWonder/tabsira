import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ProgressStages, STAGES, stageState } from './progress-stages';

describe('stageState', () => {
  it('marks earlier stages done, the running one current and the rest pending', () => {
    expect(STAGES.map((stage) => stageState(stage, 'verify'))).toEqual([
      'done',
      'done',
      'current',
      'pending',
    ]);
    expect(STAGES.map((stage) => stageState(stage, 'done'))).toEqual([
      'done',
      'done',
      'done',
      'done',
    ]);
  });
});

describe('ProgressStages', () => {
  it('names the four honest stages in order, with their state', () => {
    render(<ProgressStages current="evidence" />);
    const region = screen.getByRole('region', { name: 'مراحل إعداد البصيرة' });
    const items = within(region).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'أفهم المشهد تمّت',
      'أبحث عن الأدلة الآن',
      'أتحقق من المصادر لاحقًا',
      'أعدّ بصيرتك لاحقًا',
    ]);
    expect(items[1]).toHaveAttribute('aria-current', 'step');
  });

  it('announces the current stage politely and shows no percentage', () => {
    const { container } = render(<ProgressStages current="scene" />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent('أفهم المشهد');
    expect(container.textContent).not.toMatch(/[%٪]|\d/);
  });

  it('lights one quarter of the ring per finished stage', () => {
    const { container } = render(<ProgressStages current="compose" />);
    const arcs = Array.from(container.querySelectorAll('g[data-state]'));
    expect(arcs.map((arc) => arc.getAttribute('data-state'))).toEqual([
      'done',
      'done',
      'done',
      'current',
    ]);
    expect(container.querySelector('svg')).toHaveAttribute('data-orbit', 'working');
  });

  it('says calmly that it is slow, and offers a way out', async () => {
    const onCancel = vi.fn();
    render(<ProgressStages current="verify" slow onCancel={onCancel} className="extra" />);
    expect(screen.getByRole('status')).toHaveTextContent('وقتًا أطول من المعتاد');
    await userEvent.click(screen.getByRole('button', { name: 'ألغِ' }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('ends at rest: ready, nothing turning, no cancel, no slow note', () => {
    const { container } = render(<ProgressStages current="done" slow onCancel={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('بصيرتك جاهزة');
    expect(screen.getByRole('status')).not.toHaveTextContent('المعتاد');
    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('svg')).toHaveAttribute('data-orbit', 'sealed');
    expect(container.querySelector('[data-seal]')).not.toBeNull();
    expect(container.querySelector('li[aria-current]')).toBeNull();
  });

  it('gives each ring its own gradient', () => {
    const { container } = render(
      <>
        <ProgressStages current="scene" />
        <ProgressStages current="scene" />
      </>
    );
    const ids = Array.from(container.querySelectorAll('radialGradient')).map((g) => g.id);
    expect(new Set(ids).size).toBe(2);
    expect(container.querySelector('circle[fill^="url(#"]')?.getAttribute('fill')).toBe(
      `url(#${ids[0]})`
    );
  });
});
