import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ProfileQuestions } from './profile-questions';

describe('ProfileQuestions', () => {
  it('asks the three questions one at a time and keeps each answer', async () => {
    const onAnswer = vi.fn(async () => true);
    const onFinish = vi.fn();
    render(<ProfileQuestions onAnswer={onAnswer} onFinish={onFinish} />);
    expect(screen.getByText('السؤال 1 من 3')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: 'التفكر' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'البحث' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'التفكر' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'التعرّف إلى الإسلام' }));
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    expect(onAnswer).toHaveBeenLastCalledWith({ goals: ['discover_islam', 'research'] });
    expect(screen.getByText('السؤال 2 من 3')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'معرفة عامة' }));
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    expect(onAnswer).toHaveBeenLastCalledWith({ knowledge_level: 'general' });
    expect(screen.getByText('لا نسألك عن تاريخ ميلادك أبدًا.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'من 25 إلى 39' }));
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    expect(onAnswer).toHaveBeenLastCalledWith({ age_range: '25_39' });
    expect(onFinish).toHaveBeenCalledOnce();
    expect(screen.getByRole('status')).toHaveTextContent('شكرًا لك');
  });

  it('skips a question, or an unanswered one, without saving anything', async () => {
    const onAnswer = vi.fn(async () => true);
    render(<ProfileQuestions max={2} onAnswer={onAnswer} onFinish={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'تخطَّ' }));
    expect(screen.getByText('السؤال 2 من 2')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('skips them all at once, and stays put when an answer cannot be kept', async () => {
    const onFinish = vi.fn();
    const { unmount } = render(
      <ProfileQuestions onAnswer={vi.fn(async () => false)} onFinish={onFinish} />
    );
    await userEvent.click(screen.getByRole('checkbox', { name: 'التعليم' }));
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('السؤال 1 من 3')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'تخطَّ الأسئلة كلها' }));
    expect(onFinish).toHaveBeenCalledOnce();
    unmount();
    const { container } = render(
      <ProfileQuestions max={0} onAnswer={vi.fn()} onFinish={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
