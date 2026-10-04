import { isValidElement, type ReactElement, type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import { HADITH_TEXT, publicInsightOut, VERSE_TEXT } from '@/test/scan';
import { shareCard } from './share-card';

const ORIGIN = new URL('https://tabsira.me');
/** Every character the fixtures and messages use, as a font that covers them all would. */
const ALL = new Proxy(new Set<number>(), {
  get: (set, key) => (key === 'has' ? () => true : Reflect.get(set, key)),
}) as ReadonlySet<number>;

/** Every string in the element tree, in order. */
function strings(node: ReactNode): string[] {
  if (typeof node === 'string') {
    return [node];
  }
  if (Array.isArray(node)) {
    return node.flatMap(strings);
  }
  if (isValidElement<{ children?: ReactNode }>(node)) {
    const element = node as ReactElement<{ children?: ReactNode }>;
    const rendered =
      typeof element.type === 'function'
        ? (element.type as (props: unknown) => ReactNode)(element.props)
        : element.props.children;
    return strings(rendered);
  }
  return [];
}

describe('the share card', () => {
  it('prints the title, the references with the ruling, the explanation line, the brand, the disclosure and the link, never scripture', () => {
    const texts = strings(shareCard(publicInsightOut(), ORIGIN, ALL));
    expect(texts).toContain('عنوان البصيرة الأولى');
    expect(texts).toContain('لمحة البصيرة الأولى');
    expect(texts).toContain('القرآن');
    expect(texts).toContain('سورة اختبار، الآية 50');
    expect(texts).toContain('السنة');
    expect(texts).toContain('صحيح اختبار، رقم 1032');
    expect(texts).toContain('صحيح');
    expect(texts).toContain('النص كاملًا في الصفحة');
    expect(texts).toContain('شرح تبصرة');
    expect(texts).toContain('الماء نعمة.');
    expect(texts).toContain('تبصرة');
    expect(texts).toContain('tabsira.me/i/110000000000000002');
    expect(texts).toContain('نشرها قارئ');
    expect(texts.some((text) => text.startsWith('تبصرة أداة مدعومة'))).toBe(true);
    const joined = texts.join('\n');
    expect(joined).not.toContain(VERSE_TEXT);
    expect(joined).not.toContain(HADITH_TEXT);
    expect(joined).not.toContain('نبتة صغيرة وماء.');
  });

  it('names a prepared example, draws without an author, a ruling or texts, and drops characters the fonts lack', () => {
    const insight = publicInsightOut();
    const hadith = insight.hadith as NonNullable<typeof insight.hadith>;
    const texts = strings(
      shareCard(
        publicInsightOut({
          label: 'مثال موثّق مُعدّ',
          author: null,
          explanation: [],
          hadith: { ...hadith, hadith: { ...hadith.hadith, ruling: null } },
          title: 'عنوان 😀 مع رمز',
        }),
        ORIGIN,
        new Set(
          Array.from('عنوان مع رمزtabsira.me/i/0123456789', (c) => c.codePointAt(0) as number)
        )
      )
    );
    expect(texts).toContain('مثال موثّق مُعدّ'.replace(/[^عنوان مع رمز]/gu, '') || 'مثال موثّق مُعدّ');
    expect(texts).toContain('عنوان  مع رمز');
    expect(texts).not.toContain('نشرها قارئ');
    expect(texts).not.toContain('صحيح');
    expect(texts).not.toContain('شرح تبصرة');
    const none = strings(shareCard(publicInsightOut({ quran: null, hadith: null }), ORIGIN, ALL));
    expect(none).not.toContain('النص كاملًا في الصفحة');
    expect(none).toContain('عنوان البصيرة الأولى');
  });
});
