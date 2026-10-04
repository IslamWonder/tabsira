import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Route } from 'next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { completionOut, progressOut } from '@/test/scan';
import { CompletionPanel, type CompletionPanelProps } from './completion-panel';

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

function renderPanel(overrides: Partial<CompletionPanelProps> = {}) {
  const onContinueAsGuest = vi.fn();
  render(
    <CompletionPanel
      completion={completionOut()}
      progress={progressOut()}
      progressFailed={false}
      returnTo={'/insight/1' as Route}
      onContinueAsGuest={onContinueAsGuest}
      invitationClosed={false}
      {...overrides}
    />
  );
  return { onContinueAsGuest, region: screen.getByRole('region', { name: 'اكتملت بصيرتك' }) };
}

describe('CompletionPanel', () => {
  it('says what was earned: the new place, the day quest, the badge, with the practice disclaimer', () => {
    const { region } = renderPanel();
    expect(within(region).getByText('أضيفت «واحة الغيث» إلى عالمك')).toBeInTheDocument();
    expect(within(region).getByText(/مهمة اليوم: بصيرة اليوم/)).toBeInTheDocument();
    expect(within(region).getByText('انظر في مشهد واحد اليوم')).toBeInTheDocument();
    expect(within(region).getByText('أتممت مهمة اليوم')).toBeInTheDocument();
    expect(within(region).getByText('أول نظرة')).toBeInTheDocument();
    expect(within(region).getByText('أكملت أول مشهد.')).toBeInTheDocument();
    // A badge the learner does not hold is not listed.
    expect(within(region).queryByText('سائل')).toBeNull();
    expect(within(region).getByText('علامات على التمرين لا على الإيمان.')).toBeInTheDocument();
  });

  it('moves focus to itself and into view, so it is heard and seen', () => {
    const { region } = renderPanel();
    expect(region).toHaveFocus();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('offers the world first and another scene next, under the API labels', () => {
    const { region } = renderPanel();
    expect(within(region).getByRole('link', { name: 'افتح عالمي' })).toHaveAttribute(
      'href',
      '/world'
    );
    expect(within(region).getByRole('link', { name: 'صوّر مشهدًا آخر' })).toHaveAttribute(
      'href',
      '/'
    );
  });

  it('falls back to its own words when the API sent no options, and says a known place is known', () => {
    const { region } = renderPanel({
      completion: completionOut({
        options: [],
        first_time: false,
        place: { id: '1', region_id: 'T01', name: 'واحة الغيث', created: false },
        treasure_prepared: true,
        badges_earned: [],
      }),
      progress: null,
    });
    expect(within(region).getByRole('link', { name: 'افتح عالمي' })).toBeInTheDocument();
    expect(within(region).getByRole('link', { name: 'صوّر مشهدًا آخر' })).toBeInTheDocument();
    expect(within(region).getByText('«واحة الغيث» في عالمك من قبل')).toBeInTheDocument();
    expect(within(region).getByText(/كنز مخبوء/)).toBeInTheDocument();
    expect(within(region).queryByText(/مهمة اليوم/)).toBeNull();
  });

  it('shows no place when the world is switched off, and says when the practice could not be read', () => {
    const { region } = renderPanel({
      completion: completionOut({ place: null }),
      progress: null,
      progressFailed: true,
    });
    expect(within(region).queryByText(/عالمك/)).toBeNull();
    expect(within(region).getByText(/تعذّر عرض مهمة اليوم/)).toBeInTheDocument();
  });

  it('marks an unfinished quest step without a check, and keeps the disclaimer off when nothing was earned', () => {
    const quest = progressOut().daily_quest;
    const { region } = renderPanel({
      completion: completionOut({ badges_earned: [] }),
      progress: progressOut({
        daily_quest: {
          ...quest,
          done: false,
          steps: [{ id: 'complete', label: 'أتمّ بصيرة واحدة اليوم', done: false }],
        },
      }),
    });
    expect(within(region).getByText('أتمّ بصيرة واحدة اليوم')).toBeInTheDocument();
    expect(within(region).queryByText('أتممت مهمة اليوم')).toBeNull();
    expect(within(region).queryByText('علامات على التمرين لا على الإيمان.')).toBeNull();
  });

  it('invites a guest to save, softly, and lets them go on as one', async () => {
    const { onContinueAsGuest } = renderPanel({
      completion: completionOut({ suggest_account: 'هل تحفظ ما تعلّمته لنواصل من هنا؟' }),
    });
    await userEvent.click(screen.getByRole('button', { name: 'أتابع كضيف' }));
    expect(onContinueAsGuest).toHaveBeenCalledOnce();
    expect(screen.getByRole('link', { name: 'احفظ مساري' })).toHaveAttribute(
      'href',
      '/signup?next=%2Finsight%2F1'
    );
  });

  it('does not ask a guest again once they chose to go on, nor an account holder at all', () => {
    renderPanel({
      completion: completionOut({ suggest_account: 'هل تحفظ ما تعلّمته لنواصل من هنا؟' }),
      invitationClosed: true,
    });
    expect(screen.queryByRole('button', { name: 'أتابع كضيف' })).toBeNull();
  });
});
