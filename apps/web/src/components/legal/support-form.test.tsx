import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SupportForm } from './support-form';

const MESSAGE = 'مرحبًا، أحتاج مساعدة في حسابي من فضلكم.';

type Reply = { status: number; body?: unknown } | 'network';

/** One fake API: /auth/me answers with `me`, /support with `support`. */
function fakeApi(me: Reply, support: Reply = { status: 202 }) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const reply = String(input).endsWith('/support') ? support : me;
    if (reply === 'network') {
      throw new TypeError('offline');
    }
    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status: reply.status,
    });
  });
}

const supportCalls = (spy: ReturnType<typeof fakeApi>) =>
  spy.mock.calls.filter(([input]) => String(input).endsWith('/support'));

async function fill(user: ReturnType<typeof userEvent.setup>, topic = 'bug') {
  await user.type(screen.getByLabelText(/بريدك الإلكتروني/), 'ahmad@example.com');
  await user.selectOptions(screen.getByLabelText(/موضوع الرسالة/), topic);
  await user.type(screen.getByLabelText(/رسالتك/), MESSAGE);
}

beforeEach(() => fakeApi({ status: 401 }));
afterEach(() => vi.restoreAllMocks());

describe('SupportForm', () => {
  it('labels every field and names the form', () => {
    render(<SupportForm />);
    expect(screen.getByRole('form', { name: 'نموذج الدعم' })).toBeInTheDocument();
    expect(screen.getByLabelText(/بريدك الإلكتروني/)).toBeRequired();
    expect(screen.getByLabelText(/اسمك/)).not.toBeRequired();
    expect(screen.getByRole('combobox', { name: /موضوع الرسالة/ })).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(7);
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('keeps a honeypot in the DOM, hidden, out of the tab order and not announced', () => {
    const { container } = render(<SupportForm />);
    const trap = container.querySelector<HTMLInputElement>('input[name="website"]');
    expect(trap).not.toBeNull();
    expect(trap).toHaveAttribute('tabindex', '-1');
    expect(trap).toHaveAttribute('autocomplete', 'off');
    expect(trap?.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it('prefills the address of a signed-in reader', async () => {
    fakeApi({ status: 200, body: { email: 'me@example.com' } });
    render(<SupportForm />);
    await waitFor(() =>
      expect(screen.getByLabelText(/بريدك الإلكتروني/)).toHaveValue('me@example.com')
    );
  });

  it('does not overwrite an address the reader already typed', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      await gate;
      return new Response(JSON.stringify({ email: 'me@example.com' }), { status: 200 });
    });
    const user = userEvent.setup();
    render(<SupportForm />);
    await user.type(screen.getByLabelText(/بريدك الإلكتروني/), 'typed@example.com');
    release();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByLabelText(/بريدك الإلكتروني/)).toHaveValue('typed@example.com');
  });

  it('ignores the prefill when it arrives after the page is gone', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      await gate;
      return new Response(JSON.stringify({ email: 'me@example.com' }), { status: 200 });
    });
    const { unmount } = render(<SupportForm />);
    unmount();
    release();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  it('explains every invalid field, focuses the first, and sends nothing', async () => {
    const spy = fakeApi({ status: 401 });
    const user = userEvent.setup();
    render(<SupportForm />);
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    const email = screen.getByLabelText(/بريدك الإلكتروني/);
    expect(email).toHaveFocus();
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveAccessibleDescription(/اكتب بريدك الإلكتروني/);
    expect(screen.getByLabelText(/موضوع الرسالة/)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/رسالتك/)).toHaveAccessibleDescription(/20 أحرف على الأقل/);
    expect(screen.getByText('راجع الحقول التالية:')).toBeInTheDocument();
    expect(supportCalls(spy)).toHaveLength(0);
  });

  it('refuses a malformed address and focuses the topic, then the message', async () => {
    const user = userEvent.setup();
    render(<SupportForm />);
    await user.type(screen.getByLabelText(/بريدك الإلكتروني/), 'not-an-address');
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    expect(screen.getByLabelText(/بريدك الإلكتروني/)).toHaveAccessibleDescription(/بريدًا صحيحًا/);

    await user.clear(screen.getByLabelText(/بريدك الإلكتروني/));
    await user.type(screen.getByLabelText(/بريدك الإلكتروني/), 'a@b.co');
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    expect(screen.getByLabelText(/موضوع الرسالة/)).toHaveFocus();

    await user.selectOptions(screen.getByLabelText(/موضوع الرسالة/), 'bug');
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    expect(screen.getByLabelText(/رسالتك/)).toHaveFocus();
  });

  it('refuses a message that is too long', async () => {
    const user = userEvent.setup();
    render(<SupportForm />);
    await user.type(screen.getByLabelText(/بريدك الإلكتروني/), 'a@b.co');
    await user.selectOptions(screen.getByLabelText(/موضوع الرسالة/), 'bug');
    await user.click(screen.getByLabelText(/رسالتك/));
    await user.paste('ا'.repeat(4001));
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    expect(screen.getByLabelText(/رسالتك/)).toHaveAccessibleDescription(/أطول من 4000/);
  });

  it('counts the characters of the message', async () => {
    const user = userEvent.setup();
    render(<SupportForm />);
    await user.type(screen.getByLabelText(/رسالتك/), 'abc');
    expect(screen.getByText('3 من 4000')).toBeInTheDocument();
  });

  it('sends the form, honeypot and all, and says it was sent only for a 202', async () => {
    const spy = fakeApi({ status: 401 }, { status: 202 });
    const user = userEvent.setup();
    render(<SupportForm />);
    await fill(user);
    await user.type(screen.getByLabelText(/اسمك/), '  أحمد ');
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    const status = screen.getByRole('status');
    await waitFor(() => expect(status).toHaveTextContent('أُرسلت رسالتك إلى فريق الدعم'));
    expect(JSON.parse(String(supportCalls(spy)[0]?.[1]?.body))).toEqual({
      email: 'ahmad@example.com',
      name: 'أحمد',
      topic: 'bug',
      message: MESSAGE,
      website: '',
    });
    expect(screen.getByLabelText(/رسالتك/)).toHaveValue('');
    expect(screen.getByLabelText(/بريدك الإلكتروني/)).toHaveValue('ahmad@example.com');
  });

  it('omits an empty name, and sends what a bot wrote in the honeypot', async () => {
    const spy = fakeApi({ status: 401 });
    const user = userEvent.setup();
    const { container } = render(<SupportForm />);
    await fill(user, 'privacy');
    const trap = container.querySelector<HTMLInputElement>('input[name="website"]');
    fireEvent.change(trap as HTMLInputElement, { target: { value: 'http://spam.example' } });
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    await waitFor(() => expect(supportCalls(spy)).toHaveLength(1));
    const body = JSON.parse(String(supportCalls(spy)[0]?.[1]?.body));
    expect(body).not.toHaveProperty('name');
    expect(body.website).toBe('http://spam.example');
  });

  it.each<[string, Reply, RegExp]>([
    ['validation', { status: 422 }, /لم نقبل الرسالة/],
    ['the rate limit', { status: 429 }, /لم تُرسل رسالتك/],
    ['unavailable mail', { status: 503, body: { code: 'mail_unavailable' } }, /البريد غير متاح/],
    ['a server error', { status: 500 }, /لم تُرسل رسالتك/],
    ['no network', 'network', /تعذر الاتصال/],
  ])(
    'says honestly that nothing was sent on %s and keeps the message',
    async (_name, reply, text) => {
      fakeApi({ status: 401 }, reply);
      const user = userEvent.setup();
      render(<SupportForm />);
      await fill(user);
      await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
      const status = screen.getByRole('status');
      await waitFor(() => expect(status).toHaveTextContent(text));
      expect(status).not.toHaveTextContent('أُرسلت رسالتك إلى فريق الدعم');
      expect(screen.getByLabelText(/رسالتك/)).toHaveValue(MESSAGE);
    }
  );

  it('shows that it is sending and blocks a second press meanwhile', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/support')) {
        await gate;
        return new Response(null, { status: 202 });
      }
      return new Response(null, { status: 401 });
    });
    const user = userEvent.setup();
    render(<SupportForm />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    expect(await screen.findByRole('button', { name: 'جارٍ الإرسال' })).toBeDisabled();
    release();
    await waitFor(() => expect(screen.getByRole('button', { name: 'أرسل الرسالة' })).toBeEnabled());
  });

  it('clears the previous result when sending again', async () => {
    fakeApi({ status: 401 }, { status: 429 });
    const user = userEvent.setup();
    render(<SupportForm />);
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('كثيرة'));
    fakeApi({ status: 401 }, { status: 202 });
    await user.click(screen.getByRole('button', { name: 'أرسل الرسالة' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('أُرسلت'));
  });
});
