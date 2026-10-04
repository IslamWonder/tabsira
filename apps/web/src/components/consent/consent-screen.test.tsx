import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SiteFooter } from '@/components/app/site-footer';
import { writeConsentId } from '@/consent/cookie';
import { readConsent, type ServerConsent } from '@/consent/store';
import { apiError, mockApi, type Route } from '@/test/api';
import { POLICY, RECORD } from '@/test/fixtures';
import { ConsentScreen } from './consent-screen';

function routes(extra: Record<string, Route> = {}): Record<string, Route> {
  return { 'GET /consent/policy': { body: POLICY }, 'POST /consent': { body: RECORD }, ...extra };
}

vi.mock('next/navigation', () => ({ usePathname: () => '/world' }));

const dialog = () => screen.getByRole('dialog', { name: 'اختر ما تسمح به' });

/** What the server found on a first visit: the screen open, the policy read. */
function firstVisit(extra: Partial<ServerConsent> = {}): ServerConsent {
  return {
    consent: { status: 'asking', reason: 'first' },
    policy: POLICY,
    view: 'summary',
    failed: false,
    ...extra,
  };
}

const DECIDED: ServerConsent = {
  consent: { status: 'decided', record: RECORD },
  policy: null,
  view: 'summary',
  failed: false,
};

describe('ConsentScreen on a first visit', () => {
  it('covers the screen, with the three choices given the same weight', async () => {
    mockApi(routes());
    render(<ConsentScreen initial={firstVisit()} />);
    expect(dialog()).toHaveAttribute('aria-modal', 'true');
    expect(dialog()).toHaveFocus();
    expect(dialog()).toHaveAccessibleDescription(/بإذنك وحده/);
    const buttons = ['قبول الكل', 'رفض الكل', 'تخصيص'].map((name) =>
      within(dialog()).getByRole('button', { name })
    );
    expect(new Set(buttons.map((button) => button.className)).size).toBe(1);
    expect(within(dialog()).queryByRole('button', { name: 'أغلق دون تغيير' })).toBeNull();
    await userEvent.keyboard('{Escape}');
    expect(dialog()).toBeInTheDocument();
    expect(
      await within(dialog()).findByText('نسخة السياسة:', { exact: false })
    ).toBeInTheDocument();
  });

  it('closes once the choice is recorded', async () => {
    mockApi(routes());
    render(<ConsentScreen initial={firstVisit()} />);
    await userEvent.click(screen.getByRole('button', { name: 'قبول الكل' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(readConsent().consent.status).toBe('decided');
  });

  it('closes on a refusal even when the API cannot record it: nothing is walled', async () => {
    mockApi(routes({ 'POST /consent': 'network-error' }));
    render(<ConsentScreen initial={firstVisit()} />);
    await userEvent.click(screen.getByRole('button', { name: 'رفض الكل' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(readConsent().consent.status).toBe('dismissed');
  });

  it('says a yes could not be saved, and keeps the choices open', async () => {
    mockApi(routes({ 'POST /consent': apiError(500, 'INTERNAL_ERROR') }));
    render(<ConsentScreen initial={firstVisit()} />);
    await userEvent.click(screen.getByRole('button', { name: 'قبول الكل' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر حفظ اختيارك');
    expect(dialog()).toBeInTheDocument();
  });

  it('lets each category be chosen, the necessary one always on', async () => {
    const api = mockApi(routes());
    render(<ConsentScreen initial={firstVisit()} />);
    await userEvent.click(screen.getByRole('button', { name: 'تخصيص' }));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'اختر فئة فئة' })).toHaveFocus()
    );
    const necessary = await screen.findByRole('switch', { name: '[الضرورية]' });
    expect(necessary).toBeChecked();
    expect(necessary).toBeDisabled();
    const analytics = screen.getByRole('switch', { name: '[القياس]' });
    expect(analytics).not.toBeChecked();
    expect(screen.getByRole('switch', { name: '[السلوك]' })).not.toBeChecked();
    await userEvent.click(analytics);
    await userEvent.click(screen.getByRole('button', { name: 'احفظ اختياري' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('POST', '/consent')).toEqual([
      { policy_version: POLICY.policy_version, necessary: true, analytics: true, behaviour: false },
    ]);
  });

  it('goes back to the three choices, and copes with a policy it cannot read', async () => {
    const api = mockApi(routes({ 'GET /consent/policy': 'network-error' }));
    render(<ConsentScreen initial={firstVisit({ policy: null })} />);
    await userEvent.click(screen.getByRole('button', { name: 'تخصيص' }));
    expect(await screen.findByText('تعذّر تحميل تفاصيل الفئات الآن.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'احفظ اختياري' })).toBeDisabled();
    mockApi(routes());
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(await screen.findByRole('switch', { name: '[القياس]' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'رجوع' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'تخصيص' })).toHaveFocus());
    expect(api.requests.length).toBeGreaterThan(0);
  });

  it('says it is loading the categories meanwhile', async () => {
    mockApi(routes({ 'GET /consent/policy': () => new Promise(() => undefined) }));
    render(<ConsentScreen initial={firstVisit({ policy: null })} />);
    await userEvent.click(screen.getByRole('button', { name: 'تخصيص' }));
    expect(screen.getByText('نحمّل تفاصيل الفئات…')).toHaveAttribute('role', 'status');
  });
});

describe('ConsentScreen reopened', () => {
  function decided() {
    mockApi(routes());
    render(
      <>
        <SiteFooter />
        <ConsentScreen initial={DECIDED} />
      </>
    );
  }

  it('opens from the footer with the recorded choice, and closes unchanged', async () => {
    decided();
    expect(screen.queryByRole('dialog')).toBeNull();
    const link = screen.getByRole('button', { name: 'إعدادات ملفات تعريف الارتباط' });
    await userEvent.click(link);
    await userEvent.click(within(dialog()).getByRole('button', { name: 'تخصيص' }));
    expect(await screen.findByRole('switch', { name: '[القياس]' })).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: 'أغلق دون تغيير' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(link).toHaveFocus();
  });

  it('closes with Escape too, and opens on the summary again', async () => {
    decided();
    act(() => screen.getByRole('button', { name: 'إعدادات ملفات تعريف الارتباط' }).click());
    await userEvent.click(within(dialog()).getByRole('button', { name: 'تخصيص' }));
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    act(() => screen.getByRole('button', { name: 'إعدادات ملفات تعريف الارتباط' }).click());
    expect(within(dialog()).getByRole('button', { name: 'قبول الكل' })).toBeInTheDocument();
  });

  it('says why it asks again', () => {
    render(
      <ConsentScreen initial={firstVisit({ consent: { status: 'asking', reason: 'version' } })} />
    );
    expect(
      screen.getByText('حدّثنا سياسة ملفات تعريف الارتباط، فنسألك من جديد.')
    ).toBeInTheDocument();
  });
});

describe('ConsentScreen without JavaScript', () => {
  it('is a form that posts each choice, with where to come back and the policy version', () => {
    render(<ConsentScreen initial={firstVisit()} />);
    const form = dialog().querySelector('form') as HTMLFormElement;
    expect(form).toHaveAttribute('method', 'post');
    expect(form).toHaveAttribute('action', '/consent');
    const fields = new FormData(form);
    expect(fields.get('return')).toBe('/world');
    expect(fields.get('policy_version')).toBe(POLICY.policy_version);
    for (const [name, value] of [
      ['قبول الكل', 'accept'],
      ['رفض الكل', 'reject'],
      ['تخصيص', 'customise'],
    ]) {
      const button = screen.getByRole('button', { name });
      expect(button).toHaveAttribute('type', 'submit');
      expect(button).toHaveAttribute('name', 'choice');
      expect(button).toHaveAttribute('value', value);
    }
  });

  it('shows the customise view and a failed save as the server asked', () => {
    render(<ConsentScreen initial={firstVisit({ view: 'customise', failed: true })} />);
    const analytics = screen.getByRole('switch', { name: '[القياس]' });
    expect(analytics).toHaveAttribute('name', 'analytics');
    expect(analytics).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'احفظ اختياري' })).toHaveAttribute('value', 'save');
    expect(screen.getByRole('button', { name: 'رجوع' })).toHaveAttribute('value', 'back');
    expect(screen.getByRole('alert')).toHaveTextContent('تعذّر حفظ اختيارك');
  });

  it('says the categories could not be read when the server had no policy', () => {
    render(<ConsentScreen initial={firstVisit({ policy: null, view: 'customise' })} />);
    expect(screen.getByText('تعذّر تحميل تفاصيل الفئات الآن.')).toBeInTheDocument();
    expect(dialog().querySelector('input[name="policy_version"]')).toBeNull();
  });
});
