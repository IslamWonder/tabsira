import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { HADITH_SPANS, HADITH_TEXT } from './gallery';
import DevUiPage, { metadata } from './page.dev';
import { ViewportPreview } from './viewport-preview';

vi.mock('next/navigation', () => ({ usePathname: () => '/dev/ui' }));

function lightHalf() {
  return screen.getByRole('region', { name: 'المظهر الفاتح' });
}

function previews(viewport: string) {
  return Array.from(document.querySelectorAll<HTMLElement>(`[data-viewport="${viewport}"]`));
}

describe('the development gallery', () => {
  it('shows the real shell at the three breakpoints in both themes, as inert pictures', () => {
    render(<DevUiPage />);
    expect(metadata.robots).toEqual({ index: false, follow: false });
    // Shell: 3 sizes × 2 themes; insight: phone and desktop; layouts: 3 desktop frames.
    expect(previews('phone')).toHaveLength(3);
    expect(previews('tablet')).toHaveLength(2);
    expect(previews('desktop')).toHaveLength(6);
    for (const frame of previews('desktop')) {
      expect(frame).toHaveAttribute('inert');
      expect(frame.style.getPropertyValue('--app-height')).toMatch(/px$/);
    }
    expect(previews('phone')[0]).toHaveAttribute('data-theme', 'light');
  });

  it('shows every component in both themes', () => {
    render(<DevUiPage />);
    expect(lightHalf()).toHaveAttribute('data-theme', 'light');
    expect(screen.getByRole('region', { name: 'المظهر الداكن' })).toHaveAttribute(
      'data-theme',
      'dark'
    );
    const half = within(lightHalf());
    expect(half.getByRole('article', { name: 'القرآن' })).toBeInTheDocument();
    expect(half.getByRole('switch', { name: 'الحركة الزخرفية' })).toBeInTheDocument();
    expect(half.getByRole('button', { name: /المظهر:/ })).toBeInTheDocument();
  });

  it('shows the logo, the fields, the invitation and the questions, working', async () => {
    render(<DevUiPage />);
    const half = within(lightHalf());
    expect(half.getAllByRole('img', { name: 'تبصرة' }).length).toBeGreaterThanOrEqual(2);
    await userEvent.click(half.getByRole('switch', { name: '[خيار]' }));
    expect(half.getByRole('switch', { name: '[خيار]' })).not.toBeChecked();
    await userEvent.click(half.getByRole('radio', { name: '[جواب ثان]' }));
    expect(half.getByRole('radio', { name: '[جواب ثان]' })).toBeChecked();
    await userEvent.click(half.getByRole('checkbox', { name: /أوافق على/ }));
    expect(half.getByRole('checkbox', { name: /أوافق على/ })).toBeChecked();
    await userEvent.click(half.getByRole('button', { name: 'أتابع كضيف' }));
    expect(half.getByText('اختار الضيف أن يتابع')).toBeInTheDocument();
    await userEvent.click(half.getByRole('checkbox', { name: 'التفكر' }));
    await userEvent.click(half.getByRole('button', { name: 'احفظ وتابع' }));
    expect(half.getByText('السؤال 2 من 3')).toBeInTheDocument();
    await userEvent.click(half.getByRole('button', { name: 'تخطَّ الأسئلة كلها' }));
    expect(half.getByText(/نراعي اختياراتك في الشرح/)).toBeInTheDocument();
  });

  it('uses marked placeholders and proves the hadith spans add back up', () => {
    render(<DevUiPage />);
    const half = lightHalf();
    expect(within(half).getByText('[نص الآية يأتي من المدونة]')).toBeInTheDocument();
    const hadith = half.querySelector('[data-scripture="hadith"]');
    expect(hadith?.textContent).toBe(HADITH_TEXT);
    expect(hadith).toHaveAttribute('data-spans', 'applied');
    expect(HADITH_SPANS.map((span) => span.role)).toEqual(['chain', 'body', 'words', 'tail']);
  });

  it('selects a point on the photo and in the list', async () => {
    render(<DevUiPage />);
    const half = within(lightHalf());
    expect(half.getByText(/لم تختر بعد/)).toBeInTheDocument();
    const [point] = half.getAllByRole('button', { name: /\[عنوان البصيرة الأولى\]/ });
    await userEvent.click(point as HTMLElement);
    expect(half.getByText(/اخترت: \[عنوان البصيرة الأولى\]/)).toBeInTheDocument();
    const list = half.getByRole('region', { name: 'المس البصيرة التي لفتتك' });
    await userEvent.click(within(list).getByRole('button', { name: /الثانية/ }));
    expect(half.getByText(/اخترت: \[عنوان البصيرة الثانية\]/)).toBeInTheDocument();
  });

  it('opens and closes the sheet in the theme of its half', async () => {
    render(<DevUiPage />);
    await userEvent.click(within(lightHalf()).getByRole('button', { name: 'افتح اللوح' }));
    const dialog = screen.getByRole('dialog', { name: 'لماذا ظهر هذا؟' });
    expect(dialog.parentElement).toHaveAttribute('data-theme', 'light');
    await userEvent.click(within(dialog).getByRole('button', { name: 'أغلق' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('walks through the stages, the slow note and cancelling', async () => {
    render(<DevUiPage />);
    const half = within(lightHalf());
    const next = half.getByRole('button', { name: 'المرحلة التالية' });
    const region = half.getByRole('region', { name: 'مراحل إعداد البصيرة' });
    const status = () => within(region).getByRole('status');
    for (const label of [
      'أبحث عن الأدلة',
      'أتحقق من المصادر',
      'أعدّ بصيرتك',
      'بصيرتك جاهزة',
      'أفهم المشهد',
    ]) {
      await userEvent.click(next);
      expect(status()).toHaveTextContent(label);
    }
    await userEvent.click(half.getByRole('button', { name: 'انتظار طويل' }));
    expect(status()).toHaveTextContent('المعتاد');
    await userEvent.click(next);
    await userEvent.click(within(region).getByRole('button', { name: 'ألغِ' }));
    expect(status()).toHaveTextContent('أفهم المشهد');
  });

  it('records, defers and resets the small step, and celebrates «تمّ»', async () => {
    render(<DevUiPage />);
    const half = within(lightHalf());
    const [card] = half.getAllByRole('region', { name: 'خطوة صغيرة' });
    const step = within(card as HTMLElement);
    await userEvent.click(step.getByRole('button', { name: '[فعل الإقرار يأتي مع الخطوة]' }));
    expect(step.getByRole('status')).toHaveTextContent('سُجّل');
    const stepSection = within(half.getByRole('region', { name: 'الخطوة الصغيرة' }));
    await userEvent.click(stepSection.getByRole('button', { name: 'أعد الضبط' }));
    await userEvent.click(step.getByRole('button', { name: 'سأفعله لاحقًا' }));
    expect(step.getByRole('status')).toHaveTextContent('أجّلت');

    const doneSection = within(half.getByRole('region', { name: 'زر «تمّ»' }));
    await userEvent.click(doneSection.getByRole('button', { name: 'تمّ' }));
    expect(doneSection.getByRole('button', { name: 'تمّ' })).toBeDisabled();
    await userEvent.click(doneSection.getByRole('button', { name: 'أعد الضبط' }));
    expect(doneSection.getByRole('button', { name: 'تمّ' })).toBeEnabled();
  });

  it('receives a photo or a link from the starter, and sends nothing', async () => {
    render(<DevUiPage />);
    const half = within(lightHalf());
    const zone = half.getByRole('region', { name: /اسحب صورة/ });
    await userEvent.upload(
      within(zone).getByLabelText('اختر صورة'),
      new File(['x'], 'rain.jpg', { type: 'image/jpeg' })
    );
    expect(half.getByText(/وصل ملف: rain.jpg/)).toBeInTheDocument();
    await userEvent.click(within(zone).getByRole('button', { name: 'الصق رابط صورة' }));
    await userEvent.type(within(zone).getByLabelText('رابط الصورة'), 'example.org/a.jpg');
    await act(async () => {
      await userEvent.click(within(zone).getByRole('button', { name: 'استخدم الرابط' }));
    });
    expect(half.getByText(/وصل رابط: https:\/\/example.org\/a.jpg/)).toBeInTheDocument();
  });

  it('plays the insight frame inside its preview', () => {
    render(<DevUiPage />);
    const frame = previews('desktop').find((element) =>
      element.querySelector('article')
    ) as HTMLElement;
    const inside = within(frame);
    fireEvent.click(inside.getByRole('button', { name: 'تمّ', hidden: true }));
    expect(inside.getByRole('button', { name: 'تمّ', hidden: true })).toBeDisabled();
    fireEvent.click(inside.getByRole('button', { name: 'شارك', hidden: true }));
    expect(inside.getByRole('button', { name: 'تمّ', hidden: true })).toBeEnabled();
    fireEvent.click(inside.getByRole('button', { name: 'لماذا ظهر هذا؟', hidden: true }));
    expect(inside.getByText('[سبب الربط وحدوده يأتيان من الخادم]')).toBeVisible();
    fireEvent.click(inside.getByRole('button', { name: /ناقش البصيرة/, hidden: true }));
    expect(inside.getByText('[سبب الربط وحدوده يأتيان من الخادم]')).not.toBeVisible();
    fireEvent.click(
      inside.getByRole('button', { name: '[فعل الإقرار يأتي مع الخطوة]', hidden: true })
    );
    expect(inside.getByText('سُجّل ما صرّحت به.')).toBeInTheDocument();
  });

  it('defers the step inside the insight preview too', () => {
    render(<DevUiPage />);
    const frame = previews('phone').find((element) =>
      element.querySelector('article')
    ) as HTMLElement;
    fireEvent.click(within(frame).getByRole('button', { name: 'سأفعله لاحقًا', hidden: true }));
    expect(within(frame).getByText(/أجّلت الخطوة/)).toBeInTheDocument();
  });
});

describe('ViewportPreview', () => {
  it('scales the simulated screen down to the width it is given', () => {
    let resize: () => void = () => undefined;
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resize = callback;
        }
        observe() {}
        disconnect() {}
      }
    );
    const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(0);
    render(
      <ViewportPreview viewport="desktop" theme="dark" height={900} label="[إطار]">
        <p>[محتوى]</p>
      </ViewportPreview>
    );
    const screenBox = screen.getByText('[محتوى]').parentElement as HTMLElement;
    expect(screenBox.style.transform).toBe('scale(1)');
    width.mockReturnValue(720);
    act(() => resize());
    expect(screenBox.style.transform).toBe('scale(0.5)');
    expect((screenBox.parentElement as HTMLElement).style.height).toBe('450px');
    expect(screen.getByText('[إطار]').tagName).toBe('FIGCAPTION');
    vi.unstubAllGlobals();
  });
});
