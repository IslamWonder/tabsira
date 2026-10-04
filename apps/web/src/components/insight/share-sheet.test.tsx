import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Failure } from '@/lib/api/result';
import { insightOut } from '@/test/scan';
import { publishFailureMessage, ShareSheet, shareLinks } from './share-sheet';

const track = vi.fn();
vi.mock('@/analytics/events', () => ({ track: (...args: unknown[]) => track(...args) }));

const PUBLISHED = { published_at: '2026-10-04T09:00:00Z' };

function failure(status: number, code = 'HTTP_ERROR'): Failure {
  return { ok: false, code, status, fields: [], retryAfter: null } as unknown as Failure;
}

beforeEach(() => {
  track.mockReset();
});

describe('ShareSheet', () => {
  it('shows what becomes public and offers to publish, nothing more, while the insight is private', async () => {
    const onPublish = vi.fn();
    render(
      <ShareSheet
        open
        onClose={vi.fn()}
        insight={insightOut()}
        publishing={{ status: 'idle' }}
        onPublish={onPublish}
        onWithdraw={vi.fn()}
      />
    );
    expect(screen.getByText(/ما يظهر للجميع/)).toBeInTheDocument();
    expect(screen.queryByLabelText('رابط البصيرة')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'انشر البصيرة' }));
    expect(onPublish).toHaveBeenCalledTimes(1);
  });

  it('says it is publishing and shows why a refused insight was not published', () => {
    const { rerender } = render(
      <ShareSheet
        open
        onClose={vi.fn()}
        insight={insightOut()}
        publishing={{ status: 'saving' }}
        onPublish={vi.fn()}
        onWithdraw={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: 'ننشر…' })).toBeDisabled();
    rerender(
      <ShareSheet
        open
        onClose={vi.fn()}
        insight={insightOut()}
        publishing={{ status: 'idle', failure: failure(409, 'INSIGHT_NOT_PUBLISHABLE') }}
        onPublish={vi.fn()}
        onWithdraw={vi.fn()}
      />
    );
    expect(screen.getByRole('alert')).toHaveTextContent('لا يمكن نشر هذه البصيرة');
  });

  it('gives the link, the card, the device share sheet, copy and withdrawal once published', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { share, clipboard: { writeText } });
    const onWithdraw = vi.fn();
    render(
      <ShareSheet
        open
        onClose={vi.fn()}
        insight={insightOut(PUBLISHED)}
        publishing={{ status: 'idle' }}
        onPublish={vi.fn()}
        onWithdraw={onWithdraw}
      />
    );
    const { url, card } = shareLinks('110000000000000002');
    expect(url).toMatch(/\/insights\/110000000000000002$/);
    expect(card).toBe(`${url}/card.png`);
    const field = screen.getByLabelText<HTMLInputElement>('رابط البصيرة');
    expect(field).toHaveValue(url);
    await userEvent.click(field);
    expect(field.selectionEnd).toBe(url.length);
    expect(screen.getByRole('img', { name: 'بطاقة البصيرة للمشاركة' })).toHaveAttribute(
      'src',
      card
    );
    expect(screen.getByRole('link', { name: 'تنزيل البطاقة' })).toHaveAttribute('download');

    await userEvent.click(screen.getByRole('button', { name: 'مشاركة' }));
    expect(share).toHaveBeenCalledWith({
      title: 'عنوان البصيرة الأولى',
      text: 'بصيرة من تبصرة: عنوان البصيرة الأولى',
      url,
    });
    await userEvent.click(screen.getByRole('button', { name: 'نسخ الرابط' }));
    expect(writeText).toHaveBeenCalledWith(url);
    expect(await screen.findByText('نُسخ الرابط')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'تنزيل البطاقة' }));
    expect(track.mock.calls.map((call) => call[1])).toEqual([
      { method: 'system', kind: 'insight' },
      { method: 'link', kind: 'insight' },
      { method: 'card', kind: 'insight' },
    ]);
    await userEvent.click(screen.getByRole('button', { name: 'إلغاء النشر' }));
    expect(onWithdraw).toHaveBeenCalledTimes(1);
  });

  it('copes with a device that cannot share or copy', async () => {
    const share = vi.fn().mockRejectedValue(new Error('dismissed'));
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    Object.assign(navigator, { share, clipboard: { writeText } });
    render(
      <ShareSheet
        open
        onClose={vi.fn()}
        insight={insightOut(PUBLISHED)}
        publishing={{ status: 'saving' }}
        onPublish={vi.fn()}
        onWithdraw={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'مشاركة' }));
    await userEvent.click(screen.getByRole('button', { name: 'نسخ الرابط' }));
    expect(await screen.findByText(/لم يُنسخ الرابط/)).toBeInTheDocument();
    expect(track).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'نلغي النشر…' })).toBeDisabled();

    Object.assign(navigator, { share: undefined });
    render(
      <ShareSheet
        open
        onClose={vi.fn()}
        insight={insightOut(PUBLISHED)}
        publishing={{ status: 'idle' }}
        onPublish={vi.fn()}
        onWithdraw={vi.fn()}
      />
    );
    expect(screen.getAllByRole('button', { name: 'مشاركة' })).toHaveLength(1);
  });

  it('names the reason a publication failed in the owner words', () => {
    expect(publishFailureMessage(failure(409))).toMatch(/لا يمكن نشر/);
    expect(publishFailureMessage(failure(403, 'EMAIL_NOT_VERIFIED'))).toMatch(/وثّق بريدك/);
    expect(publishFailureMessage(failure(401))).toMatch(/سجّل الدخول/);
    expect(publishFailureMessage(failure(403))).toMatch(/غير متاح/);
    expect(publishFailureMessage(failure(404))).toMatch(/غير متاح/);
    expect(publishFailureMessage(failure(500))).toMatch(/حاول بعد قليل/);
  });
});
