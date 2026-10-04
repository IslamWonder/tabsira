import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { StepCard, type StepStatus } from './step-card';

function renderStep(status?: StepStatus) {
  const onConfirm = vi.fn();
  const onDefer = vi.fn();
  render(
    <StepCard
      body="[الخطوة]"
      confirmLabel="[الإقرار]"
      onConfirm={onConfirm}
      onDefer={onDefer}
      status={status}
      className="extra"
    />
  );
  return { onConfirm, onDefer };
}

describe('StepCard', () => {
  it('offers exactly two answers: doing it, or putting it off', async () => {
    const { onConfirm, onDefer } = renderStep();
    const section = screen.getByRole('region', { name: 'خطوة صغيرة' });
    expect(section).toHaveClass('extra');
    expect(screen.getAllByRole('button')).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: '[الإقرار]' }));
    await userEvent.click(screen.getByRole('button', { name: 'سأفعله لاحقًا' }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onDefer).toHaveBeenCalledOnce();
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('blocks a second tap while saving', () => {
    renderStep('saving');
    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled();
    }
    expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('أحفظ');
  });

  it('announces success only once saved, and removes the buttons', () => {
    renderStep('saved');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByRole('status')).toHaveTextContent('سُجّل ما صرّحت به.');
  });

  it('confirms a deferral without blame, and keeps «done» for when the reader comes back', () => {
    renderStep('deferred');
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual([
      '[الإقرار]',
    ]);
    expect(screen.getByRole('status')).toHaveTextContent('أجّلت الخطوة');
  });

  it('labels the step as the API does, and says what the API says the answer means', () => {
    const { rerender } = render(
      <StepCard
        body="[الخطوة]"
        label="[من السنة]"
        confirmLabel="[الإقرار]"
        onConfirm={vi.fn()}
        onDefer={vi.fn()}
        status="saved"
        statusText="[ما يعنيه الجواب]"
      />
    );
    expect(screen.getByText('[من السنة]')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('[ما يعنيه الجواب]');
    rerender(
      <StepCard
        body="[الخطوة]"
        confirmLabel="[الإقرار]"
        onConfirm={vi.fn()}
        onDefer={vi.fn()}
        error="[لم يُحفظ]"
      />
    );
    expect(screen.queryByText('[من السنة]')).toBeNull();
    expect(screen.getByRole('alert')).toHaveTextContent('[لم يُحفظ]');
  });
});
