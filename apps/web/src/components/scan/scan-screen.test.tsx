import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Failure } from '@/lib/api/result';
import type { RunStage, ScanControls, ScanView } from '@/lib/scan/use-scan';
import { scanOut } from '@/test/scan';
import { ScanScreen } from './scan-screen';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push }),
}));

let controls: ScanControls;
vi.mock('@/lib/scan/use-scan', () => ({ useScan: () => controls }));

const failure = (code: Failure['code'], status = 400): Failure => ({
  ok: false,
  code,
  status,
  fields: [],
  retryAfter: null,
});

function setControls(view: ScanView, extra: Partial<ScanControls> & { stage?: RunStage } = {}) {
  controls = {
    view,
    stage: 'queued',
    slow: false,
    acting: false,
    reload: vi.fn(),
    focus: vi.fn().mockResolvedValue(null),
    clarify: vi.fn().mockResolvedValue(null),
    ...extra,
  };
  return controls;
}

const running = (overrides = {}) =>
  ({
    phase: 'running',
    scan: scanOut({ status: 'running', outcome: null, insights: [], ...overrides }),
  }) as const;
const ready = (overrides = {}) => ({ phase: 'ready', scan: scanOut(overrides) }) as const;

beforeEach(() => {
  push.mockClear();
});

describe('ScanScreen: reading and failing', () => {
  it('says it is opening the scan, with no photo yet', () => {
    setControls({ phase: 'loading' });
    render(<ScanScreen scanId="1" />);
    expect(screen.getByRole('heading', { level: 1, name: 'مشهدك' })).toBeInTheDocument();
    expect(screen.getByText('نفتح مشهدك…')).toBeInTheDocument();
    expect(screen.getByText('تظهر صورتك هنا بعد أن نفحصها.')).toBeInTheDocument();
  });

  it('says why the scan cannot be read, and reads it again on request', async () => {
    const { reload } = setControls({ phase: 'lost', failure: failure('NOT_FOUND', 404) });
    render(<ScanScreen scanId="1" />);
    expect(screen.getByRole('alert')).toHaveTextContent('لم نجد هذا المشهد عندك');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(reload).toHaveBeenCalledOnce();
    expect(screen.getByRole('link', { name: 'جرّب مشهدًا آخر' })).toHaveAttribute('href', '/');
  });

  it('says a failed run in words that tell what to do, never as «no result»', () => {
    setControls({
      phase: 'failed',
      scan: scanOut({ status: 'failed', outcome: null, error_code: 'SOURCE_UNAVAILABLE' }),
      code: 'SOURCE_UNAVAILABLE',
    });
    render(<ScanScreen scanId="1" />);
    expect(
      screen.getByRole('heading', { level: 2, name: 'لم تكتمل قراءة المشهد' })
    ).toBeInTheDocument();
    expect(screen.getByText(/لا نعوّض ذلك بنص مولّد/)).toBeInTheDocument();
    expect(screen.queryByText('لم أجد صلة موثوقة بهذا المشهد بعد')).toBeNull();
    expect(screen.getByRole('link', { name: 'جرّب مشهدًا آخر' })).toBeInTheDocument();
  });
});

describe('ScanScreen: the stages', () => {
  it('shows the four honest stages, the current one, and a calm note when it is slow', () => {
    setControls(running(), { stage: 'searching', slow: true });
    render(<ScanScreen scanId="1" />);
    const stages = screen.getByRole('region', { name: 'مراحل إعداد البصيرة' });
    const items = within(stages).getAllByRole('listitem');
    expect(items).toHaveLength(4);
    expect(items[1]).toHaveAttribute('aria-current', 'step');
    expect(
      within(stages).getByText('ما زلنا نعمل على طلبك، وقد يستغرق وقتًا أطول من المعتاد.')
    ).toBeInTheDocument();
    expect(document.querySelector('[data-edge-glow="active"]')).not.toBeNull();
  });

  it('says it waits its turn before any stage has begun', () => {
    setControls(running());
    render(<ScanScreen scanId="1" />);
    expect(screen.getAllByText('ننتظر دور مشهدك').length).toBeGreaterThan(0);
  });

  it('sweeps the photo with light once it may be shown, and lets the reader leave', async () => {
    setControls(running(), { stage: 'verifying' });
    render(<ScanScreen scanId="1" />);
    expect(screen.getByRole('img', { name: 'صورتك التي أرسلتها' })).toBeInTheDocument();
    expect(document.querySelector('[data-scan="active"]')).not.toBeNull();
    expect(document.querySelectorAll('[data-point-id]')).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: 'ألغِ' }));
    expect(push).toHaveBeenCalledWith('/');
  });

  it('shows no photo before the verdict on its sensitivity', () => {
    setControls(running({ image: { available: false, width: null, height: null, url: null } }), {
      stage: 'understanding',
    });
    render(<ScanScreen scanId="1" />);
    expect(screen.queryByRole('img', { name: 'صورتك التي أرسلتها' })).toBeNull();
    expect(screen.getByText('تظهر صورتك هنا بعد أن نفحصها.')).toBeInTheDocument();
  });

  it('never shows the photo of a sensitive scene, and says it is neither shown nor kept', () => {
    setControls(
      running({
        sensitive: true,
        image: { available: false, width: null, height: null, url: null },
      }),
      { stage: 'searching' }
    );
    render(<ScanScreen scanId="1" />);
    expect(screen.queryByRole('img', { name: 'صورتك التي أرسلتها' })).toBeNull();
    expect(screen.getAllByText('لن نعرض هذه الصورة ولن نحفظها. نعرض لك المعنى وحده.').length).toBe(
      2
    );
  });

  it('never shows the photo of a sensitive scene even if the API still held its address', () => {
    setControls(ready({ sensitive: true }));
    render(<ScanScreen scanId="1" />);
    expect(screen.queryByRole('img', { name: 'صورتك التي أرسلتها' })).toBeNull();
    expect(screen.getByText('عنوان البصيرة الأولى')).toBeInTheDocument();
  });

  it('shows a declared simulation prominently', () => {
    setControls(running({ engine: 'demo', engine_label: '[محاكاة معلنة]' }), {
      stage: 'searching',
    });
    render(<ScanScreen scanId="1" />);
    expect(screen.getByRole('note')).toHaveTextContent('[محاكاة معلنة]');
  });
});

describe('ScanScreen: the insights', () => {
  it('lists the insights and puts a point on the photo for each one that has a place in it', async () => {
    setControls(
      ready({
        insights: [
          ...scanOut().insights,
          {
            id: '110000000000000004',
            title: 'عنوان بلا موضع',
            glimpse: 'لمحة بلا موضع',
            anchor: null,
            relation: 'direct',
            relation_label: 'صلة مباشرة',
            completed: false,
          },
        ],
        awaiting_verification: 1,
      })
    );
    render(<ScanScreen scanId="1" />);
    expect(document.querySelectorAll('[data-point-id]')).toHaveLength(2);
    const list = screen.getByRole('region', { name: 'المس البصيرة التي لفتتك' });
    expect(within(list).getAllByRole('button')).toHaveLength(3);
    expect(within(list).getByText('تمّت · لمحة البصيرة الثانية')).toBeInTheDocument();
    expect(screen.getByText('نبتة صغيرة في أصيص')).toBeInTheDocument();
    expect(screen.getByText(/بانتظار التحقق من حكمه في الدرر/)).toBeInTheDocument();
    await userEvent.click(within(list).getByRole('button', { name: /عنوان بلا موضع/ }));
    expect(push).toHaveBeenCalledWith('/insight/110000000000000004');
  });

  it('opens an insight from its point on the photo', async () => {
    setControls(ready());
    render(<ScanScreen scanId="1" />);
    await userEvent.click(
      document.querySelector('[data-point-id="110000000000000002"]') as HTMLElement
    );
    expect(push).toHaveBeenCalledWith('/insight/110000000000000002');
  });

  it('has no scene description and no waiting note when the scan gave none', () => {
    setControls(ready({ description: null }));
    render(<ScanScreen scanId="1" />);
    expect(screen.queryByText('ما رأيناه في المشهد')).toBeNull();
    expect(screen.queryByText(/بانتظار التحقق/)).toBeNull();
  });

  it('says the photo left the temporary store, and keeps the insights', () => {
    setControls(ready({ image: { available: false, width: 800, height: 600, url: null } }));
    render(<ScanScreen scanId="1" />);
    expect(screen.getByText(/مضت ساعة فمُسحت الصورة/)).toBeInTheDocument();
    expect(screen.getByText('عنوان البصيرة الثانية')).toBeInTheDocument();
  });

  it('shows the photo only when its size is known too', () => {
    setControls(ready({ image: { available: true, width: null, height: null, url: '/x' } }));
    render(<ScanScreen scanId="1" />);
    expect(screen.queryByRole('img', { name: 'صورتك التي أرسلتها' })).toBeNull();
  });

  it('has no focus button when the scene found nothing to point at', () => {
    setControls(ready({ entities: [] }));
    render(<ScanScreen scanId="1" />);
    expect(screen.queryByRole('button', { name: 'وضّح ما تقصد' })).toBeNull();
  });
});

describe('ScanScreen: the single question', () => {
  function renderQuestion(extra: Partial<ScanControls> = {}) {
    const state = setControls(
      ready({
        outcome: 'needs_clarification',
        insights: [],
        clarification_question: 'ما الذي يحدث هنا بالضبط؟',
      }),
      extra
    );
    render(<ScanScreen scanId="1" />);
    return state;
  }

  it('asks the one question the API asked, and sends the answer', async () => {
    const { clarify } = renderQuestion();
    expect(screen.getByText('ما الذي يحدث هنا بالضبط؟')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('جوابك'), '  أسقي النبتة ');
    await userEvent.click(screen.getByRole('button', { name: 'أجب وأكمل' }));
    expect(clarify).toHaveBeenCalledWith('أسقي النبتة');
  });

  it('asks for an answer before sending anything', async () => {
    const { clarify } = renderQuestion();
    await userEvent.click(screen.getByRole('button', { name: 'أجب وأكمل' }));
    expect(clarify).not.toHaveBeenCalled();
    expect(screen.getByText('اكتب جوابك أولًا.')).toBeInTheDocument();
  });

  it('says why an answer was refused, and keeps what was typed', async () => {
    const { clarify } = renderQuestion({
      clarify: vi.fn().mockResolvedValue(failure('SCAN_BUSY', 409)),
    });
    await userEvent.type(screen.getByLabelText('جوابك'), 'جواب');
    await userEvent.click(screen.getByRole('button', { name: 'أجب وأكمل' }));
    expect(
      await screen.findByText('ما زلنا نحلّل هذا المشهد. انتظر حتى ينتهي.')
    ).toBeInTheDocument();
    expect(screen.getByLabelText('جوابك')).toHaveValue('جواب');
    expect(clarify).toHaveBeenCalledOnce();
  });

  it('does not send a second answer while one is on its way', async () => {
    const { clarify } = renderQuestion({ acting: true });
    expect(screen.getByRole('button', { name: 'أرسل جوابك…' })).toBeDisabled();
    await userEvent.type(screen.getByLabelText('جوابك'), 'جواب');
    fireEvent.submit(screen.getByLabelText('جوابك').closest('form') as HTMLFormElement);
    expect(clarify).not.toHaveBeenCalled();
  });

  it('still shows the form when the API sent no question text', () => {
    setControls(
      ready({ outcome: 'needs_clarification', insights: [], clarification_question: null })
    );
    render(<ScanScreen scanId="1" />);
    expect(screen.getByLabelText('جوابك')).toBeInTheDocument();
  });
});

describe('ScanScreen: no reliable link', () => {
  it('says so as a result of its own, with a way to focus and a way to try another scene', () => {
    setControls(ready({ outcome: 'no_relevant_evidence', insights: [], awaiting_verification: 2 }));
    render(<ScanScreen scanId="1" />);
    expect(
      screen.getByRole('heading', { level: 2, name: 'لم أجد صلة موثوقة بهذا المشهد بعد' })
    ).toBeInTheDocument();
    expect(screen.getByText(/لا نكمل بنص بعيد/)).toBeInTheDocument();
    expect(screen.getByText(/بانتظار التحقق من حكمه في الدرر/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'وضّح ما تقصد' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'جرّب مشهدًا آخر' })).toBeInTheDocument();
  });

  it('treats a finished scan with insights promised but none given as no reliable link', () => {
    setControls(ready({ outcome: 'insights', insights: [] }));
    render(<ScanScreen scanId="1" />);
    expect(
      screen.getByRole('heading', { level: 2, name: 'لم أجد صلة موثوقة بهذا المشهد بعد' })
    ).toBeInTheDocument();
    expect(screen.queryByText(/بانتظار التحقق/)).toBeNull();
  });
});

describe('ScanScreen: choosing a focus', () => {
  async function startFocus(extra: Partial<ScanControls> = {}, overrides = {}) {
    const state = setControls(ready(overrides), extra);
    render(<ScanScreen scanId="1" />);
    await userEvent.click(screen.getByRole('button', { name: 'وضّح ما تقصد' }));
    return state;
  }

  it('shows a box on each thing found with a place, and every thing in a list', async () => {
    await startFocus();
    const stage = screen.getByRole('group', { name: 'الأشياء في الصورة' });
    expect(within(stage).getAllByRole('button')).toHaveLength(2);
    const list = screen.getByRole('list', { name: 'ما وجدناه في الصورة' });
    expect(within(list).getAllByRole('button')).toHaveLength(3);
    expect(within(list).getAllByText('مُرجَّح')).toHaveLength(2);
    expect(document.querySelectorAll('[data-point-id]')).toHaveLength(0);
  });

  it('chooses from the photo or the list, and looks again at the chosen thing', async () => {
    const { focus } = await startFocus();
    const confirm = screen.getByRole('button', { name: 'انظر إلى هذا' });
    expect(confirm).toBeDisabled();
    await userEvent.click(
      within(screen.getByRole('group', { name: 'الأشياء في الصورة' })).getByRole('button', {
        name: 'نبتة',
      })
    );
    expect(screen.getByText('اخترت: نبتة')).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByRole('list', { name: 'ما وجدناه في الصورة' })).getByRole('button', {
        name: /أصيص/,
      })
    );
    expect(screen.getByText('اخترت: أصيص')).toBeInTheDocument();
    await userEvent.click(confirm);
    expect(focus).toHaveBeenCalledWith('e2');
    expect(screen.queryByRole('button', { name: 'انظر إلى هذا' })).toBeNull();
  });

  it('says why a focus was refused and stays in the choice', async () => {
    await startFocus({ focus: vi.fn().mockResolvedValue(failure('SCAN_BUSY', 409)) });
    await userEvent.click(
      within(screen.getByRole('list', { name: 'ما وجدناه في الصورة' })).getByRole('button', {
        name: /ضوء/,
      })
    );
    await userEvent.click(screen.getByRole('button', { name: 'انظر إلى هذا' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('ما زلنا نحلّل هذا المشهد');
    expect(screen.getByRole('button', { name: 'انظر إلى هذا' })).toBeInTheDocument();
  });

  it('goes back without choosing anything', async () => {
    await startFocus();
    await userEvent.click(screen.getByRole('button', { name: 'ارجع' }));
    expect(screen.getByRole('region', { name: 'المس البصيرة التي لفتتك' })).toBeInTheDocument();
  });

  it('holds the choice while it is sent', async () => {
    await startFocus({ acting: true });
    expect(screen.getByRole('button', { name: 'أنظر…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'ارجع' })).toBeDisabled();
  });

  it('offers the choice as a list alone when the photo may not be shown', async () => {
    await startFocus({}, { sensitive: true });
    expect(screen.queryByRole('group', { name: 'الأشياء في الصورة' })).toBeNull();
    expect(screen.getByRole('list', { name: 'ما وجدناه في الصورة' })).toBeInTheDocument();
  });
});
