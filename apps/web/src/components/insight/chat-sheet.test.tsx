import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Failure } from '@/lib/api/result';
import type { Insight } from '@/lib/scan/api';
import { chatReply, HADITH_TEXT, insightOut, sha256, VERSE_TEXT } from '@/test/scan';
import { ChatSheet } from './chat-sheet';

function bytes(text: string) {
  return Array.from(new TextEncoder().encode(text));
}

/** A message whose answer found the insight fixture's texts, as the API returns them. */
function replyWithTexts() {
  const { quran, hadith } = insightOut();
  const found = {
    quran: quran === null ? null : { tag: quran.tag, verse: quran.verse },
    hadith: hadith === null ? null : { tag: hadith.tag, hadith: hadith.hadith },
  };
  return { ...chatReply().message, kind: 'new_search' as const, ...found };
}

function failure(code: Failure['code'], status: number): Failure {
  return { ok: false, code, status, fields: [], retryAfter: null };
}

function chatWith(overrides: Partial<Insight['chat']> = {}): Insight['chat'] {
  return { ...insightOut().chat, ...overrides };
}

function renderChat(chat: Insight['chat'], onAsk = vi.fn().mockResolvedValue(null)) {
  render(<ChatSheet open onClose={vi.fn()} insightTitle="[العنوان]" chat={chat} onAsk={onAsk} />);
  return { onAsk, sheet: screen.getByRole('dialog', { name: 'ناقش البصيرة' }) };
}

describe('ChatSheet', () => {
  it('says which insight it is about, how many questions are used, and the AI disclosure', () => {
    const { sheet } = renderChat(chatWith({ used: 1, remaining: 2 }));
    expect(sheet).toHaveAccessibleDescription('[العنوان]');
    expect(within(sheet).getByRole('status')).toHaveTextContent('استُعمل 1 من 3');
    expect(within(sheet).getByText('لم تسأل شيئًا بعد.')).toBeInTheDocument();
    expect(within(sheet).getByText(/ليست مفتيًا ولا عالمًا/)).toBeInTheDocument();
  });

  it('lists the questions asked with their answers', () => {
    const reply = chatReply().message;
    const { sheet } = renderChat(chatWith({ used: 1, remaining: 2, messages: [reply] }));
    expect(within(sheet).getByText('ما معنى هذا؟')).toBeInTheDocument();
    expect(within(sheet).getByText('جواب الاختبار.')).toBeInTheDocument();
    expect(within(sheet).queryByText('لم تسأل شيئًا بعد.')).toBeNull();
  });

  it('renders a message without texts as before: no evidence card under the answer', () => {
    const reply = chatReply().message;
    const { sheet } = renderChat(chatWith({ used: 1, remaining: 2, messages: [reply] }));
    expect(within(sheet).queryByRole('article')).toBeNull();
    expect(sheet.querySelector('[data-scripture]')).toBeNull();
  });

  it('shows a found verse and hadith under the answer, byte for byte, matching their stored hashes', () => {
    const reply = replyWithTexts();
    const { sheet } = renderChat(chatWith({ used: 1, remaining: 2, messages: [reply] }));
    const item = within(sheet).getByText('جواب الاختبار.').closest('li') as HTMLElement;
    const quran = within(item).getByRole('article', { name: 'القرآن' });
    const sunnah = within(item).getByRole('article', { name: 'السنة' });
    const verse = quran.querySelector('[data-scripture="quran"]')?.textContent as string;
    const hadith = sunnah.querySelector('[data-scripture="hadith"]')?.textContent as string;
    expect(bytes(verse)).toEqual(bytes(VERSE_TEXT));
    expect(bytes(hadith)).toEqual(bytes(HADITH_TEXT));
    expect(sha256(verse)).toBe(reply.quran?.verse.sha256);
    expect(sha256(hadith)).toBe(reply.hadith?.hadith.sha256);
    expect(within(quran).getByText('سورة اختبار، الآية 50')).toBeInTheDocument();
    expect(within(sunnah).getByRole('link', { name: /تحقق في الدرر/ })).toHaveAttribute(
      'href',
      'https://dorar.net/hadith/search?q=test'
    );
    // The cards sit under the sheet's own h2 title.
    expect(within(quran).getByRole('heading', { level: 3 })).toHaveTextContent('القرآن');
    expect(within(sunnah).getByRole('heading', { level: 3 })).toHaveTextContent('السنة');
  });

  it('shows a found verse alone, with no notice and no hadith card', () => {
    const reply = { ...replyWithTexts(), hadith: null };
    const { sheet } = renderChat(chatWith({ used: 1, remaining: 2, messages: [reply] }));
    expect(within(sheet).getByRole('article', { name: 'القرآن' })).toBeInTheDocument();
    expect(within(sheet).queryByRole('article', { name: 'السنة' })).toBeNull();
    expect(within(sheet).getAllByRole('status')).toHaveLength(1);
  });

  it('shows a found hadith alone', () => {
    const reply = { ...replyWithTexts(), quran: null };
    const { sheet } = renderChat(chatWith({ used: 1, remaining: 2, messages: [reply] }));
    expect(within(sheet).queryByRole('article', { name: 'القرآن' })).toBeNull();
    expect(within(sheet).getByRole('article', { name: 'السنة' })).toBeInTheDocument();
  });

  it('sends one question with a key, and clears the field once it is answered', async () => {
    const { onAsk, sheet } = renderChat(chatWith());
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), '  ما المعنى؟  ');
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    expect(onAsk).toHaveBeenCalledOnce();
    const [message, key] = onAsk.mock.calls[0] as [string, string];
    expect(message).toBe('ما المعنى؟');
    expect(key).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(within(sheet).getByLabelText('سؤالك')).toHaveValue('');
  });

  it('asks for a question before sending anything', async () => {
    const { onAsk, sheet } = renderChat(chatWith());
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    expect(onAsk).not.toHaveBeenCalled();
    expect(within(sheet).getByRole('alert')).toHaveTextContent('اكتب سؤالك أولًا.');
    expect(within(sheet).getByLabelText('سؤالك')).toBeInvalid();
  });

  it('sends the same key again after a failure that may be mended, so it counts once', async () => {
    const onAsk = vi
      .fn()
      .mockResolvedValueOnce(failure('NETWORK', 0))
      .mockResolvedValueOnce(failure('INTERNAL_ERROR', 500))
      .mockResolvedValueOnce(null);
    const { sheet } = renderChat(chatWith(), onAsk);
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), 'سؤال');
    const send = within(sheet).getByRole('button', { name: 'اسأل' });
    await userEvent.click(send);
    expect(within(sheet).getByRole('alert')).toHaveTextContent('تعذّر الوصول إلى تبصرة');
    await userEvent.click(send);
    await userEvent.click(send);
    const keys = onAsk.mock.calls.map((call) => call[1]);
    expect(new Set(keys).size).toBe(1);
    expect(within(sheet).getByRole('alert')).toBeEmptyDOMElement();
  });

  it('takes a new key after the API refused the question, and says why', async () => {
    const onAsk = vi
      .fn()
      .mockResolvedValueOnce(failure('CHAT_ANSWER_REJECTED', 422))
      .mockResolvedValueOnce(null);
    const { sheet } = renderChat(chatWith(), onAsk);
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), 'سؤال');
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    expect(within(sheet).getByRole('alert')).toHaveTextContent('أعد صياغته');
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    expect(onAsk.mock.calls[0]?.[1]).not.toBe(onAsk.mock.calls[1]?.[1]);
  });

  it('ignores a second send while one is on its way', async () => {
    let release: (value: null) => void = () => undefined;
    const onAsk = vi.fn(
      () =>
        new Promise<null>((resolve) => {
          release = resolve;
        })
    );
    const { sheet } = renderChat(chatWith(), onAsk);
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), 'سؤال');
    const form = within(sheet).getByLabelText('سؤالك').closest('form') as HTMLFormElement;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(onAsk).toHaveBeenCalledOnce();
    expect(within(sheet).getByRole('button', { name: 'أجيب…' })).toBeDisabled();
    release(null);
    expect(await within(sheet).findByRole('button', { name: 'اسأل' })).toBeEnabled();
  });

  it('says the discussion is complete after the last answer, with no field left', () => {
    const { sheet } = renderChat(chatWith({ used: 3, remaining: 0 }));
    expect(within(sheet).queryByLabelText('سؤالك')).toBeNull();
    expect(within(sheet).getAllByRole('status')[1]).toHaveTextContent(
      'اكتمل النقاش حول هذه البصيرة'
    );
  });

  it('says so when the chat is switched off', () => {
    const { sheet } = renderChat(chatWith({ enabled: false }));
    expect(within(sheet).queryByLabelText('سؤالك')).toBeNull();
    expect(within(sheet).getByText('النقاش غير متاح الآن.')).toBeInTheDocument();
    expect(within(sheet).queryByText('اكتمل النقاش حول هذه البصيرة')).toBeNull();
  });
});
