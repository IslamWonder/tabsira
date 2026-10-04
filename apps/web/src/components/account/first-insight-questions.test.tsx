import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { markDeviceQuestionsAsked, readDeviceAnswers } from '@/account/device-answers';
import { forgetSession, setGuest, setSignedIn } from '@/account/session';
import { mockApi } from '@/test/api';
import { PROFILE, USER } from '@/test/fixtures';
import { FirstInsightQuestions } from './first-insight-questions';

const TITLE = 'كيف تحب أن تتعلم وتتأمل؟';

beforeEach(() => {
  forgetSession();
  window.localStorage.clear();
});

describe('FirstInsightQuestions: a guest', () => {
  it('is asked once, keeps the answers on the device, and is not asked again', async () => {
    setGuest();
    const { unmount } = render(<FirstInsightQuestions max={3} />);
    expect(await screen.findByRole('heading', { name: TITLE })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: 'التفكر' }));
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    await userEvent.click(screen.getByRole('button', { name: 'تخطَّ' }));
    await userEvent.click(screen.getByRole('button', { name: 'تخطَّ' }));
    expect(screen.getByRole('status')).toHaveTextContent('شكرًا لك');
    expect(readDeviceAnswers()).toEqual({ goals: ['reflection'] });
    unmount();
    const { container } = render(<FirstInsightQuestions max={3} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('skipping them all keeps every answer unknown and marks them asked', async () => {
    setGuest();
    render(<FirstInsightQuestions max={3} />);
    await userEvent.click(await screen.findByRole('button', { name: 'تخطَّ الأسئلة كلها' }));
    expect(readDeviceAnswers()).toEqual({});
  });

  it('asks nothing when the device already says they were asked, or when the setting is zero', () => {
    setGuest();
    markDeviceQuestionsAsked();
    const first = render(<FirstInsightQuestions max={3} />);
    expect(first.container).toBeEmptyDOMElement();
    first.unmount();
    window.localStorage.clear();
    const second = render(<FirstInsightQuestions max={0} />);
    expect(second.container).toBeEmptyDOMElement();
  });
});

describe('FirstInsightQuestions: an account', () => {
  it('asks when the profile was never asked, saves each answer, and records the end', async () => {
    setSignedIn(USER);
    const api = mockApi({
      'GET /profile': { body: PROFILE },
      'PATCH /profile': { body: { ...PROFILE, questions_asked: true } },
    });
    render(<FirstInsightQuestions max={2} />);
    expect(await screen.findByRole('heading', { name: TITLE })).toBeInTheDocument();
    expect(screen.getByText('السؤال 1 من 2')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: 'البحث' }));
    await userEvent.click(screen.getByRole('button', { name: 'احفظ وتابع' }));
    await userEvent.click(screen.getByRole('button', { name: 'تخطَّ' }));
    await waitFor(async () =>
      expect(await api.bodies('PATCH', '/profile')).toEqual([
        { goals: ['research'] },
        { questions_asked: true },
      ])
    );
    expect(readDeviceAnswers()).toBeNull();
  });

  it('asks nothing when the profile says they were asked, or cannot be read', async () => {
    setSignedIn(USER);
    mockApi({ 'GET /profile': { body: { ...PROFILE, questions_asked: true } } });
    const asked = render(<FirstInsightQuestions max={3} />);
    await waitFor(() => expect(asked.container).toBeEmptyDOMElement());
    asked.unmount();
    mockApi({ 'GET /profile': 'network-error' });
    const unread = render(<FirstInsightQuestions max={3} />);
    await waitFor(() => expect(unread.container).toBeEmptyDOMElement());
  });

  it('stays silent while the session is unknown', () => {
    const { container } = render(<FirstInsightQuestions max={3} />);
    expect(container).toBeEmptyDOMElement();
  });
});
