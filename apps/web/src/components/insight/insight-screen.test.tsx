import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { apiError, mockApi, type Route } from '@/test/api';
import {
  chatReply,
  completionOut,
  HADITH_TEXT,
  insightOut,
  progressOut,
  scanOut,
  VERSE_TEXT,
} from '@/test/scan';
import { InsightScreen } from './insight-screen';
import { shareLinks } from './share-sheet';

const ID = '110000000000000002';
const SCAN = '110000000000000001';

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

function serve(insight = insightOut(), extra: Record<string, Route> = {}) {
  return mockApi({
    [`GET /insights/${ID}`]: { body: insight },
    [`GET /scans/${SCAN}`]: { body: scanOut() },
    ...extra,
  });
}

async function open(insight = insightOut(), extra: Record<string, Route> = {}) {
  const api = serve(insight, extra);
  render(<InsightScreen insightId={ID} />);
  await screen.findByRole('heading', { level: 1, name: insight.title });
  return api;
}

describe('InsightScreen: the page', () => {
  it('says it is opening, then shows the insight in the order of tajriba §6', async () => {
    serve();
    render(<InsightScreen insightId={ID} />);
    expect(screen.getByRole('status')).toHaveTextContent('نفتح بصيرتك');
    const title = await screen.findByRole('heading', { level: 1, name: 'عنوان البصيرة الأولى' });
    expect(screen.getByText('لمحة البصيرة الأولى')).toBeInTheDocument();
    expect(screen.getByText('صلة مباشرة')).toBeInTheDocument();
    expect(screen.getByText('نبتة صغيرة وماء.')).toBeInTheDocument();
    const quran = screen.getByRole('article', { name: 'القرآن' });
    const sunnah = screen.getByRole('article', { name: 'السنة' });
    const explanation = screen.getByRole('region', { name: 'شرح تبصرة' });
    const why = screen.getByRole('button', { name: 'لماذا ظهر هذا؟' });
    const step = screen.getByRole('region', { name: /خطوة صغيرة/ });
    const done = screen.getByRole('button', { name: 'تمّ' });
    const follows = (a: Element, b: Element) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(
      [title, quran, sunnah, explanation, why, step, done].every((node, index, list) =>
        index === 0 ? true : follows(list[index - 1] as Element, node)
      )
    ).toBe(true);
    expect(screen.getByText(/ليست مفتيًا ولا عالمًا/)).toBeInTheDocument();
  });

  it('renders the scripture byte for byte, as the API returns it', async () => {
    serve();
    const { container } = render(<InsightScreen insightId={ID} />);
    await screen.findByRole('heading', { level: 1 });
    expect(container.querySelector('[data-scripture="quran"]')?.textContent).toBe(VERSE_TEXT);
    expect(container.querySelector('[data-scripture="hadith"]')?.textContent).toBe(HADITH_TEXT);
  });

  it('shows the photo of its scan, and the way back to that scan', async () => {
    await open();
    expect(screen.getByRole('img', { name: 'صورة المشهد' })).toHaveAttribute(
      'src',
      expect.stringContaining(`/scans/${SCAN}/image`)
    );
    expect(screen.getAllByRole('link', { name: 'العودة إلى المشهد' })[0]).toHaveAttribute(
      'href',
      `/scan/${SCAN}`
    );
  });

  it('holds the place of the photo while it is asked for, with the way back', async () => {
    await open(insightOut(), { [`GET /scans/${SCAN}`]: () => new Promise(() => undefined) });
    expect(screen.getAllByText('نفتح بصيرتك…').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'العودة إلى المشهد' })[0]).toHaveAttribute(
      'href',
      `/scan/${SCAN}`
    );
  });

  it('shows the prepared rain photo and its label for a tutorial insight, and goes back home', async () => {
    await open(
      insightOut({
        origin: 'tutorial',
        scan_id: null,
        engine: 'prepared',
        label: '[مثال موثّق مُعدّ]',
      })
    );
    expect(
      await screen.findByRole('img', { name: 'نبتة زيتون صغيرة تتلقى قطرات المطر' })
    ).toBeInTheDocument();
    expect(screen.getByText('[مثال موثّق مُعدّ]')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'العودة إلى المشهد' })[0]).toHaveAttribute(
      'href',
      '/'
    );
  });

  it('shows a declared simulation prominently', async () => {
    await open(insightOut({ engine: 'demo', label: '[محاكاة معلنة للتطوير]' }));
    expect(screen.getByRole('note')).toHaveTextContent('[محاكاة معلنة للتطوير]');
  });

  it('never shows the photo of a sensitive scene, and says so', async () => {
    await open(insightOut({ image: { sensitive: true, url: null } }));
    expect(await screen.findByText('لا نعرض صورة هذا المشهد ولا نحفظها.')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'صورة المشهد' })).toBeNull();
  });

  it('says why a photo that left the store is not there, and what stays', async () => {
    const gone = scanOut({ image: { available: false, width: 800, height: 600, url: null } });
    await open(insightOut(), { [`GET /scans/${SCAN}`]: { body: gone } });
    expect(await screen.findByText(/مُسحت الصورة من خادمنا/)).toBeInTheDocument();
  });

  it('leaves out the parts the insight does not have', async () => {
    await open(
      insightOut({
        explanation: [],
        small_step: null,
        anchor: null,
        quran: null,
        hadith: null,
        hadith_status: 'none',
      })
    );
    expect(screen.queryByRole('region', { name: /خطوة صغيرة/ })).toBeNull();
    expect(screen.queryByRole('region', { name: 'شرح تبصرة' })).toBeNull();
    expect(screen.queryByRole('article', { name: 'القرآن' })).toBeNull();
    expect(screen.queryByRole('article', { name: 'السنة' })).toBeNull();
  });

  it('says why it cannot open the insight, and tries again', async () => {
    let answered = 0;
    mockApi({
      [`GET /insights/${ID}`]: () => {
        answered += 1;
        return answered === 1 ? apiError(404, 'NOT_FOUND') : { body: insightOut() };
      },
      [`GET /scans/${SCAN}`]: { body: scanOut() },
    });
    render(<InsightScreen insightId={ID} />);
    expect(await screen.findByText(/لم نجد هذا المشهد عندك/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'جرّب مشهدًا آخر' })).toHaveAttribute('href', '/');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'عنوان البصيرة الأولى' })
    ).toBeInTheDocument();
  });
});

describe('InsightScreen: why, the chat and the step', () => {
  it('opens «لماذا ظهر هذا؟» as a sheet and returns to the same place on closing', async () => {
    await open();
    const button = screen.getByRole('button', { name: 'لماذا ظهر هذا؟' });
    await userEvent.click(button);
    const sheet = screen.getByRole('dialog', { name: 'لماذا ظهر هذا؟' });
    expect(within(sheet).getByText('الإحياء بالماء')).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: 'أغلق' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(button).toHaveFocus();
  });

  it('asks in the chat, shows the answer and the count, and says used n of 3', async () => {
    await open(insightOut(), { [`POST /insights/${ID}/chat`]: { body: chatReply() } });
    expect(screen.getByRole('button', { name: /ناقش البصيرة/ })).toHaveTextContent('استُعمل 0 من 3');
    await userEvent.click(screen.getByRole('button', { name: /ناقش البصيرة/ }));
    const sheet = screen.getByRole('dialog', { name: 'ناقش البصيرة' });
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), 'ما معنى هذا؟');
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    expect(await within(sheet).findByText('جواب الاختبار.')).toBeInTheDocument();
    expect(within(sheet).getAllByText('استُعمل 1 من 3').length).toBeGreaterThan(0);
    await userEvent.click(within(sheet).getByRole('button', { name: 'أغلق' }));
    expect(screen.getByRole('button', { name: /ناقش البصيرة/ })).toHaveTextContent('استُعمل 1 من 3');
  });

  it('labels the step as the API does, and records «done» with what the API says it means', async () => {
    await open(insightOut(), {
      [`POST /insights/${ID}/action`]: { body: { state: 'done', at: null, means: '[ما يعنيه]' } },
    });
    const step = screen.getByRole('region', { name: /خطوة صغيرة/ });
    expect(within(step).getByText('من السنة')).toBeInTheDocument();
    await userEvent.click(within(step).getByRole('button', { name: 'نفّذته' }));
    await waitFor(() => expect(within(step).getByRole('status')).toHaveTextContent('[ما يعنيه]'));
    expect(within(step).queryByRole('button')).toBeNull();
  });

  it('records «later» and keeps «done» for when the reader returns', async () => {
    await open(insightOut(), {
      [`POST /insights/${ID}/action`]: { body: { state: 'later', at: null, means: '[حُفظ]' } },
    });
    const step = screen.getByRole('region', { name: /خطوة صغيرة/ });
    await userEvent.click(within(step).getByRole('button', { name: 'سأفعله لاحقًا' }));
    await waitFor(() => expect(within(step).getByRole('status')).toHaveTextContent('[حُفظ]'));
    expect(
      within(step)
        .getAllByRole('button')
        .map((button) => button.textContent)
    ).toEqual(['نفّذته']);
  });

  it('says why the step was not recorded', async () => {
    await open(insightOut(), { [`POST /insights/${ID}/action`]: 'network-error' });
    await userEvent.click(screen.getByRole('button', { name: 'نفّذته' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر الوصول إلى تبصرة');
  });
});

describe('InsightScreen: «تمّ»', () => {
  it('saves once, shows what was earned, and leaves the button done', async () => {
    const api = await open(insightOut(), {
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      'GET /me/progress': { body: progressOut() },
    });
    const done = screen.getByRole('button', { name: 'تمّ' });
    await userEvent.dblClick(done);
    const panel = await screen.findByRole('region', { name: 'اكتملت بصيرتك' });
    expect(within(panel).getByText('أضيفت «واحة الغيث» إلى عالمك')).toBeInTheDocument();
    expect(await within(panel).findByText('أول نظرة')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'تمّ' })).toBeDisabled();
    expect(api.requests.filter((request) => request.url.includes('/complete'))).toHaveLength(1);
  });

  it('invites a guest to save, once, softly', async () => {
    await open(insightOut(), {
      [`POST /insights/${ID}/complete`]: {
        body: completionOut({ suggest_account: 'هل تحفظ ما تعلّمته لنواصل من هنا؟' }),
      },
      'GET /me/progress': { body: progressOut() },
    });
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    await userEvent.click(await screen.findByRole('button', { name: 'أتابع كضيف' }));
    expect(screen.queryByRole('button', { name: 'أتابع كضيف' })).toBeNull();
    expect(screen.getByRole('region', { name: 'اكتملت بصيرتك' })).toBeInTheDocument();
  });

  it('says the save failed, announces nothing, and lets the reader try again', async () => {
    await open(insightOut(), { [`POST /insights/${ID}/complete`]: apiError(503, 'SAVE_FAILED') });
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('لم تُحفظ البصيرة');
    expect(screen.queryByRole('region', { name: 'اكتملت بصيرتك' })).toBeNull();
    expect(screen.getByRole('button', { name: 'تمّ' })).toBeEnabled();
  });

  it('shows an insight completed earlier as done, with the way to the world', async () => {
    await open(insightOut({ completed_at: '2026-10-04T08:05:00Z' }));
    expect(screen.getByRole('button', { name: 'تمّ' })).toBeDisabled();
    expect(screen.getByText('اكتملت هذه البصيرة')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'افتح عالمي' })).toHaveAttribute('href', '/world');
  });
});

describe('InsightScreen: sharing', () => {
  it('publishes from the share sheet, then withdraws, and keeps a refusal in the sheet', async () => {
    const published = {
      insight_id: ID,
      published: true,
      published_at: '2026-10-04T09:00:00Z',
      path: `/insights/${ID}`,
    };
    let publishAnswer: Route = { body: published };
    const api = await open(insightOut(), {
      [`PUT /insights/${ID}/publication`]: () =>
        typeof publishAnswer === 'object' ? publishAnswer : { status: 500 },
      [`DELETE /insights/${ID}/publication`]: {
        body: { insight_id: ID, published: false, published_at: null, path: null },
      },
    });
    await userEvent.click(screen.getByRole('button', { name: 'شارك البصيرة' }));
    await userEvent.click(screen.getByRole('button', { name: 'انشر البصيرة' }));
    expect(await screen.findByLabelText('رابط البصيرة')).toHaveValue(shareLinks(ID).url);
    expect(screen.getByRole('button', { name: 'البصيرة منشورة' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'إلغاء النشر' }));
    expect(await screen.findByRole('button', { name: 'انشر البصيرة' })).toBeInTheDocument();
    expect(api.requests.filter((r) => r.method === 'DELETE')).toHaveLength(1);

    publishAnswer = apiError(409, 'INSIGHT_NOT_PUBLISHABLE');
    await userEvent.click(screen.getByRole('button', { name: 'انشر البصيرة' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('لا يمكن نشر هذه البصيرة');
  });

  it('closes the share sheet again', async () => {
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'شارك البصيرة' }));
    expect(screen.getByRole('button', { name: 'انشر البصيرة' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: messages.sheet.close }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'انشر البصيرة' })).toBeNull());
  });
});
