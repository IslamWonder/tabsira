import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { insightOut } from '@/test/scan';
import { EngineLabel } from './engine-label';
import { ExplanationSections } from './explanation-sections';
import { PhotoPlaceholder } from './photo-placeholder';
import { PlaceReveal } from './place-reveal';
import { WhySheet } from './why-sheet';

describe('EngineLabel', () => {
  it('shows nothing for a live analysis', () => {
    const { container } = render(<EngineLabel engine="pipeline" label={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a prepared example as a calm label, in the API words', () => {
    render(<EngineLabel engine="prepared" label="[مثال موثّق مُعدّ]" />);
    expect(screen.getByText('[مثال موثّق مُعدّ]')).toBeInTheDocument();
    expect(screen.queryByRole('note')).toBeNull();
  });

  it('shows a simulation as a bordered notice that cannot be missed', () => {
    render(<EngineLabel engine="demo" label="[محاكاة معلنة]" />);
    const note = screen.getByRole('note');
    expect(note).toHaveTextContent('محاكاة');
    expect(note).toHaveTextContent('[محاكاة معلنة]');
    expect(note).toHaveClass('border-2');
  });
});

describe('PhotoPlaceholder', () => {
  it('says why there is no photo, with the way back on a phone when given', () => {
    render(<PhotoPlaceholder note="[لا صورة]" backHref="/" />);
    expect(screen.getByText('[لا صورة]')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'العودة إلى المشهد' })).toHaveAttribute('href', '/');
  });

  it('has no way back of its own when the page brings one', () => {
    render(<PhotoPlaceholder note="[لا صورة]" className="extra" />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('fills the stage it is in, or keeps the height of the insight photo', () => {
    const { container, rerender } = render(<PhotoPlaceholder note="[لا صورة]" fill />);
    expect(container.firstElementChild).toHaveClass('h-full');
    rerender(<PhotoPlaceholder note="[لا صورة]" />);
    expect(container.firstElementChild).toHaveClass('h-[330px]');
  });
});

describe('PlaceReveal', () => {
  it('lifts a veil only from a place this completion made', () => {
    const { container, rerender } = render(<PlaceReveal created />);
    expect(container.querySelector('[data-mist]')).not.toBeNull();
    expect(container.firstElementChild).toHaveAttribute('data-place', 'new');
    rerender(<PlaceReveal created={false} className="extra" />);
    expect(container.querySelector('[data-mist]')).toBeNull();
    expect(container.firstElementChild).toHaveAttribute('data-place', 'known');
  });
});

describe('ExplanationSections', () => {
  it('keeps each part under the API label, apart from what the photo shows', () => {
    const insight = insightOut();
    render(<ExplanationSections tag={insight.explanation_tag} parts={insight.explanation} />);
    const region = screen.getByRole('region', { name: 'شرح تبصرة' });
    expect(within(region).getByText('القيمة')).toBeInTheDocument();
    expect(within(region).getByText('ماذا تضيف الآية')).toBeInTheDocument();
    expect(within(region).getByText('تذكّر ذلك حين ترى المطر.')).toBeInTheDocument();
    expect(within(region).queryByText('ما ظهر')).toBeNull();
  });

  it('shows nothing when only «ما ظهر» is left', () => {
    const { container } = render(
      <ExplanationSections
        tag="شرح تبصرة"
        parts={[{ section: 'seen', label: 'ما ظهر', text: 'نبتة' }]}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('WhySheet', () => {
  it('answers in order: the scene, the meaning, the sources, the limits, the personal choice', () => {
    render(<WhySheet open onClose={vi.fn()} insight={insightOut()} />);
    const sheet = screen.getByRole('dialog', { name: 'لماذا ظهر هذا؟' });
    expect(sheet).toHaveAccessibleDescription('عنوان البصيرة الأولى');
    const headings = within(sheet)
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent);
    expect(headings).toEqual([
      'ما ظهر في المشهد',
      'المعنى',
      'المصادر',
      'حدود هذه الصلة',
      'التخصيص',
    ]);
    expect(within(sheet).getByText('تربة رطبة')).toBeInTheDocument();
    expect(within(sheet).getByText('الإحياء بالماء')).toBeInTheDocument();
    expect(
      within(sheet).getByText('صلة مباشرة، وجه الصلة: أثر الماء في الأرض')
    ).toBeInTheDocument();
    expect(within(sheet).getByText('صلة بالفعل، وجه الصلة: رؤية المطر')).toBeInTheDocument();
    expect(within(sheet).getByText('لم يُبنَ هذا الاختيار على ملفك.')).toBeInTheDocument();
  });

  it('says what a personal choice was built on, when it was', () => {
    const base = insightOut();
    render(
      <WhySheet
        open
        onClose={vi.fn()}
        insight={insightOut({ why: { ...base.why, personalised_because: '[سبب التخصيص]' } })}
      />
    );
    expect(
      screen.getByText('اختيارٌ بُني على ما صرّحت به في ملفك: [سبب التخصيص]')
    ).toBeInTheDocument();
  });

  it('leaves out what it has none of, and closes', async () => {
    const onClose = vi.fn();
    const base = insightOut();
    render(
      <WhySheet
        open
        onClose={onClose}
        insight={insightOut({
          quran: null,
          hadith: base.hadith && { ...base.hadith, why: null },
          why: { ...base.why, visible_clues: [], limits: [] },
        })}
      />
    );
    const sheet = screen.getByRole('dialog');
    expect(within(sheet).queryByText('ما ظهر في المشهد')).toBeNull();
    expect(within(sheet).queryByText('حدود هذه الصلة')).toBeNull();
    expect(within(sheet).queryByText(/وجه الصلة/)).toBeNull();
    expect(within(sheet).getByText('السنة')).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: 'أغلق' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('leaves the sources out when there are none, and a source line without its match', () => {
    const base = insightOut();
    const { rerender } = render(
      <WhySheet open onClose={vi.fn()} insight={insightOut({ quran: null, hadith: null })} />
    );
    expect(screen.queryByText('المصادر')).toBeNull();
    rerender(
      <WhySheet
        open
        onClose={vi.fn()}
        insight={insightOut({
          quran: base.quran && {
            ...base.quran,
            why: { relation: 'direct', relation_label: 'صلة مباشرة', matched_on: '' },
          },
          hadith: null,
        })}
      />
    );
    expect(screen.getByText('صلة مباشرة')).toBeInTheDocument();
  });
});
