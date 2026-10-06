import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { forgetSession, readSession, setGuest, setSignedIn } from '@/account/session';
import { messages } from '@/messages';
import { apiError, mockApi, type Route } from '@/test/api';
import { PROFILE, USER } from '@/test/fixtures';
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

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const ID = '110000000000000002';
const SCAN = '110000000000000001';

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  forgetSession();
  push.mockClear();
  window.localStorage.clear();
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
    await open(insightOut({ image: { sensitive: true, url: null, has_photo: false } }));
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

  it('opens the profile form when the chat says the profile is not complete', async () => {
    setSignedIn(USER);
    await open(insightOut(), { [`POST /insights/${ID}/chat`]: apiError(403, 'profile_required') });
    await userEvent.click(screen.getByRole('button', { name: /ناقش البصيرة/ }));
    const sheet = screen.getByRole('dialog', { name: 'ناقش البصيرة' });
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), 'ما معنى هذا؟');
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    await waitFor(() =>
      expect(readSession()).toMatchObject({ user: { profile_completed: false } })
    );
  });

  it('sends to sign-up when the chat says an account is required', async () => {
    setSignedIn(USER);
    await open(insightOut(), { [`POST /insights/${ID}/chat`]: apiError(403, 'account_required') });
    await userEvent.click(screen.getByRole('button', { name: /ناقش البصيرة/ }));
    const sheet = screen.getByRole('dialog', { name: 'ناقش البصيرة' });
    await userEvent.type(within(sheet).getByLabelText('سؤالك'), 'ما معنى هذا؟');
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسأل' }));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(`/signup?next=%2Finsight%2F${ID}&reason=chat`)
    );
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

const PAGE = `https://tabsira.test/insights/${ID}`;
const PUBLISHED = {
  insight_id: ID,
  published: true,
  published_at: '2026-10-06T09:00:00Z',
  path: `/insights/${ID}`,
};

function stubShare(share: unknown, clipboard?: unknown) {
  vi.stubGlobal('navigator', { ...navigator, share, clipboard });
}

async function finished(extra: Record<string, Route> = {}, insight = insightOut()) {
  const api = await open(insight, {
    [`POST /insights/${ID}/complete`]: { body: completionOut() },
    'GET /me/progress': { body: progressOut() },
    'GET /profile': { body: { ...PROFILE, questions_asked: true } },
    ...extra,
  });
  await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
  const panel = await screen.findByRole('region', { name: 'اكتملت بصيرتك' });
  return { api, panel };
}

const puts = (api: { requests: Request[] }) =>
  api.requests.filter((request) => request.method === 'PUT');

describe('InsightScreen: sharing', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shares in one tap from the footer button: the system dialog opens inside the tap, then the publication lands', async () => {
    setSignedIn(USER);
    const order: string[] = [];
    const share = vi.fn(async () => {
      order.push('share');
    });
    stubShare(share);
    const api = serve(insightOut(), {
      [`PUT /insights/${ID}/publication`]: () => {
        order.push('publish');
        return { body: PUBLISHED };
      },
    });
    render(<InsightScreen insightId={ID} />);
    await screen.findByRole('heading', { level: 1, name: insightOut().title });
    const button = screen.getByRole('button', { name: 'شارك' });
    fireEvent.click(button);
    fireEvent.click(button);
    // Called synchronously, before any await of the network.
    expect(share).toHaveBeenCalledOnce();
    expect(share).toHaveBeenCalledWith({
      title: insightOut().title,
      text: insightOut().title,
      url: PAGE,
    });
    await waitFor(() => expect(puts(api)).toHaveLength(1));
    expect(order).toEqual(['share', 'publish']);
    expect(screen.queryByRole('dialog')).toBeNull();
    // Already public now: a later tap shares without publishing again.
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(share).toHaveBeenCalledTimes(2);
    expect(puts(api)).toHaveLength(1);
  });

  it('shares an insight already public without publishing it', async () => {
    setSignedIn(USER);
    const share = vi.fn().mockResolvedValue(undefined);
    stubShare(share);
    const api = await open(insightOut({ published_at: '2026-10-04T09:00:00Z' }));
    await userEvent.click(screen.getByRole('button', { name: 'شارك' }));
    expect(share).toHaveBeenCalledOnce();
    expect(puts(api)).toHaveLength(0);
  });

  it('says the API refusal when the publication fails, so the owner knows the link will not open', async () => {
    setSignedIn(USER);
    stubShare(vi.fn().mockResolvedValue(undefined));
    await open(insightOut(), {
      [`PUT /insights/${ID}/publication`]: apiError(409, 'INSIGHT_NOT_PUBLISHABLE'),
    });
    await userEvent.click(screen.getByRole('button', { name: 'شارك' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('لا يمكن نشر هذه البصيرة');
  });

  it('copies the link and says so when the browser has no share dialog', async () => {
    setSignedIn(USER);
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubShare(undefined, { writeText });
    await open(insightOut(), { [`PUT /insights/${ID}/publication`]: { body: PUBLISHED } });
    await userEvent.click(screen.getByRole('button', { name: 'شارك' }));
    expect(await screen.findByText('نُسخ الرابط.')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(PAGE);
  });

  it('offers no sharing to a guest, whom the API refuses, and says so after «تمّ»', async () => {
    setGuest();
    await open(insightOut(), {
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      'GET /me/progress': { body: progressOut() },
    });
    expect(screen.queryByRole('button', { name: 'شارك' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    const panel = await screen.findByRole('region', { name: 'اكتملت بصيرتك' });
    expect(within(panel).queryByRole('button', { name: 'شارك' })).toBeNull();
    expect(within(panel).getByText(/سجّل الدخول لتشارك البصيرة/)).toBeInTheDocument();
  });

  it('offers no sharing for an insight that is not from the real analysis, and says so', async () => {
    setSignedIn(USER);
    await open(insightOut({ engine: 'demo' }), {
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      'GET /me/progress': { body: progressOut() },
      'GET /profile': { body: { ...PROFILE, questions_asked: true } },
    });
    expect(screen.queryByRole('button', { name: 'شارك' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    const panel = await screen.findByRole('region', { name: 'اكتملت بصيرتك' });
    expect(within(panel).getByText(/المثال المُعدّ لا يُشارك/)).toBeInTheDocument();
  });

  it('shows the share button with its icon and the hint after «تمّ», and shares in one tap', async () => {
    setSignedIn(USER);
    const share = vi.fn().mockResolvedValue(undefined);
    stubShare(share);
    const { api, panel } = await finished({
      [`PUT /insights/${ID}/publication`]: { body: PUBLISHED },
    });
    expect(within(panel).getByText(/المشاركة تنشر للبصيرة صفحة عامة/)).toBeInTheDocument();
    const button = within(panel).getByRole('button', { name: 'شارك' });
    expect(button.querySelector('svg')).not.toBeNull();
    await userEvent.click(button);
    expect(share).toHaveBeenCalledWith({
      title: insightOut().title,
      text: insightOut().title,
      url: PAGE,
    });
    await waitFor(() => expect(puts(api)).toHaveLength(1));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the refusal in the panel when the publication fails, and opens the sheet from the options link', async () => {
    setSignedIn(USER);
    stubShare(vi.fn().mockResolvedValue(undefined));
    const { panel } = await finished({
      [`PUT /insights/${ID}/publication`]: apiError(409, 'INSIGHT_NOT_PUBLISHABLE'),
    });
    await userEvent.click(within(panel).getByRole('button', { name: 'شارك' }));
    expect(await within(panel).findByRole('alert')).toHaveTextContent('لا يمكن نشر هذه البصيرة');
    await userEvent.click(within(panel).getByRole('button', { name: 'خيارات النشر' }));
    expect(screen.getByRole('dialog', { name: 'شارك البصيرة' })).toBeInTheDocument();
  });

  it('publishes from the sheet and the screen then shares without publishing again', async () => {
    setSignedIn(USER);
    const share = vi.fn().mockResolvedValue(undefined);
    stubShare(share);
    const { api, panel } = await finished({
      [`PUT /insights/${ID}/publication`]: { body: PUBLISHED },
      [`DELETE /insights/${ID}/publication`]: {
        body: { insight_id: ID, published: false, published_at: null, path: null },
      },
    });
    await userEvent.click(within(panel).getByRole('button', { name: 'خيارات النشر' }));
    const sheet = screen.getByRole('dialog', { name: 'شارك البصيرة' });
    await userEvent.click(within(sheet).getByRole('button', { name: 'انشر وشارك' }));
    await within(sheet).findByRole('button', { name: 'اسحب النشر' });
    await userEvent.click(within(sheet).getByRole('button', { name: 'اسحب النشر' }));
    await within(sheet).findByText(/سُحبت البصيرة/);
    await userEvent.click(within(sheet).getByRole('button', { name: 'أغلق' }));
    await userEvent.click(within(panel).getByRole('button', { name: 'شارك' }));
    // Withdrawn, so the tap publishes again.
    await waitFor(() => expect(puts(api)).toHaveLength(2));
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

  it('sends a guest who opens the chat of their own scan to sign-up (decision 64)', async () => {
    setGuest();
    await open(insightOut({ engine: 'pipeline' }));
    await userEvent.click(screen.getByRole('button', { name: /ناقش البصيرة/ }));
    expect(push).toHaveBeenCalledWith(`/signup?next=%2Finsight%2F${ID}&reason=chat`);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps the chat of the prepared tutorial open to a guest', async () => {
    setGuest();
    await open(insightOut({ engine: 'prepared' }));
    await userEvent.click(screen.getByRole('button', { name: /ناقش البصيرة/ }));
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'ناقش البصيرة' })).toBeInTheDocument();
  });

  it('invites a guest to save, without a guest button', async () => {
    await open(insightOut(), {
      [`POST /insights/${ID}/complete`]: {
        body: completionOut({ suggest_account: 'هل تحفظ ما تعلّمته لنواصل من هنا؟' }),
      },
      'GET /me/progress': { body: progressOut() },
    });
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    expect(
      await screen.findByRole('link', { name: 'أنشئ حسابي واحفظ بصيرتي' })
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'أتابع كضيف' })).toBeNull();
    expect(screen.getByRole('region', { name: 'اكتملت بصيرتك' })).toBeInTheDocument();
  });

  it('no longer asks the optional first-insight questions: the mandatory profile covers them', async () => {
    setGuest();
    await open(insightOut(), {
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      'GET /me/progress': { body: progressOut() },
    });
    await userEvent.click(screen.getByRole('button', { name: 'تمّ' }));
    await screen.findByRole('region', { name: 'اكتملت بصيرتك' });
    expect(screen.queryByRole('region', { name: 'كيف تحب أن تتعلم وتتأمل؟' })).toBeNull();
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

describe('InsightScreen: rating the insight', () => {
  const F = messages.insightPage.feedback;
  const RATED = {
    helpful: false,
    reasons: ['wrong_text' as const],
    note: 'الآية بعيدة',
    updated_at: '2026-10-05T10:00:00Z',
  };
  const done = insightOut({ completed_at: '2026-10-04T08:05:00Z' });

  it('asks nothing before the end, then saves a yes at once and says thank you', async () => {
    const api = await open(done, {
      [`PUT /insights/${ID}/feedback`]: {
        body: { helpful: true, reasons: [], note: null, updated_at: '2026-10-05T10:00:00Z' },
      },
    });
    expect(screen.getByText(F.question)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: F.yes }));
    expect(await screen.findByText(F.thanks)).toBeInTheDocument();
    expect(await api.bodies('PUT', `/insights/${ID}/feedback`)).toEqual([
      { helpful: true, reasons: [], note: null },
    ]);
  });

  it('does not ask on an insight that is not done yet', async () => {
    await open();
    expect(screen.queryByText(F.question)).toBeNull();
  });

  it('opens the sheet on a no, sends the reasons and the note, and refuses an empty choice', async () => {
    const api = await open(done, { [`PUT /insights/${ID}/feedback`]: { body: RATED } });
    await userEvent.click(screen.getByRole('button', { name: F.no }));
    const sheet = await screen.findByRole('dialog', { name: F.title });
    expect(within(sheet).getByRole('button', { name: F.notHelpful })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await userEvent.click(within(sheet).getByRole('checkbox', { name: F.reasons.wrong_text }));
    await userEvent.click(within(sheet).getByRole('checkbox', { name: F.reasons.other }));
    await userEvent.click(within(sheet).getByRole('checkbox', { name: F.reasons.other }));
    await userEvent.type(within(sheet).getByLabelText(F.noteLabel), 'الآية بعيدة');
    await userEvent.click(within(sheet).getByRole('button', { name: F.send }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('PUT', `/insights/${ID}/feedback`)).toEqual([
      { helpful: false, reasons: ['wrong_text'], note: 'الآية بعيدة' },
    ]);
    expect(screen.getByText(F.thanks)).toBeInTheDocument();
  });

  it('opens from the small menu at any time, and a yes there sends no reason', async () => {
    const api = await open(insightOut(), {
      [`PUT /insights/${ID}/feedback`]: {
        body: { helpful: true, reasons: [], note: null, updated_at: '2026-10-05T10:00:00Z' },
      },
    });
    await userEvent.click(screen.getByRole('button', { name: F.menu }));
    const sheet = await screen.findByRole('dialog', { name: F.title });
    expect(within(sheet).getByRole('button', { name: F.send })).toBeDisabled();
    // Submitting without a choice (Enter in a field) sends nothing.
    fireEvent.submit(
      within(sheet).getByRole('button', { name: F.send }).closest('form') as HTMLFormElement
    );
    expect(await api.bodies('PUT', `/insights/${ID}/feedback`)).toEqual([]);
    await userEvent.click(within(sheet).getByRole('button', { name: F.notHelpful }));
    await userEvent.click(within(sheet).getByRole('checkbox', { name: F.reasons.offensive }));
    await userEvent.click(within(sheet).getByRole('button', { name: F.helpful }));
    expect(within(sheet).queryByRole('checkbox')).toBeNull();
    await userEvent.click(within(sheet).getByRole('button', { name: F.send }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await api.bodies('PUT', `/insights/${ID}/feedback`)).toEqual([
      { helpful: true, reasons: [], note: null },
    ]);
  });

  it('shows an earlier rating with a way to change it, the sheet opening on it', async () => {
    await open({ ...done, feedback: RATED });
    expect(screen.getByText(F.ratedNotHelpful)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: F.change }));
    const sheet = await screen.findByRole('dialog', { name: F.title });
    expect(within(sheet).getByRole('checkbox', { name: F.reasons.wrong_text })).toBeChecked();
    expect(within(sheet).getByLabelText(F.noteLabel)).toHaveValue('الآية بعيدة');
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('says a useful earlier rating plainly', async () => {
    await open({ ...done, feedback: { ...RATED, helpful: true, reasons: [], note: null } });
    expect(screen.getByText(F.ratedHelpful)).toBeInTheDocument();
  });

  it('says so when the rating could not be saved, and holds a note that is too long', async () => {
    await open(done, { [`PUT /insights/${ID}/feedback`]: apiError(503, 'SAVE_FAILED') });
    await userEvent.click(screen.getByRole('button', { name: F.yes }));
    expect(await screen.findByRole('alert')).toHaveTextContent(F.failed);

    await userEvent.click(screen.getByRole('button', { name: F.no }));
    const sheet = await screen.findByRole('dialog', { name: F.title });
    const field = within(sheet).getByLabelText(F.noteLabel);
    await userEvent.click(field);
    await userEvent.paste('ن'.repeat(301));
    expect(within(sheet).getByRole('button', { name: F.send })).toBeDisabled();
  });
});
