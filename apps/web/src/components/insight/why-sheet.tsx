import type { ReactNode } from 'react';
import { Chip } from '@/components/ui/chip';
import { Sheet } from '@/components/ui/sheet';
import type { Insight } from '@/lib/scan/api';
import { messages } from '@/messages';

const T = messages.insightPage.why;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="m-0 font-semibold text-[0.9375rem] text-fg-soft">{title}</h3>
      {children}
    </section>
  );
}

function Items({ items }: { items: readonly string[] }) {
  return (
    <ul className="m-0 flex list-disc flex-col gap-1 ps-5 text-[1rem] text-fg leading-[1.85]">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export interface WhySheetProps {
  open: boolean;
  onClose: () => void;
  insight: Insight;
}

/**
 * the why-this sheet (tajriba S03, LUX-04, LUX-16): the scene first, then the
 * meaning, then the source, in that order, with what each source matched on and
 * how it relates, then the limits of the link and whether a personal choice
 * shaped it. No confidence number is shown as certainty. The title of the
 * insight stays in the sheet's description, so the reader knows which insight
 * it is about (Working memory).
 */
export function WhySheet({ open, onClose, insight }: WhySheetProps) {
  const sources = [
    insight.quran === null
      ? null
      : { key: 'quran', tag: T.sourceQuran, tone: 'quran' as const, why: insight.quran.why },
    insight.hadith === null
      ? null
      : { key: 'sunnah', tag: T.sourceSunnah, tone: 'sunnah' as const, why: insight.hadith.why },
  ].flatMap((source) => source ?? []);
  const { why } = insight;

  return (
    <Sheet open={open} onClose={onClose} title={T.title} description={insight.title}>
      <div className="flex flex-col gap-5 pb-2">
        {why.visible_clues.length === 0 ? null : (
          <Section title={T.clues}>
            <Items items={why.visible_clues} />
          </Section>
        )}
        <Section title={T.concept}>
          <p className="m-0 text-[1rem] text-fg leading-[1.85]">{why.concept}</p>
        </Section>
        {sources.length === 0 ? null : (
          <Section title={T.sources}>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {sources.map((source) => (
                <li key={source.key} className="flex flex-col items-start gap-1">
                  <Chip tone={source.tone}>{source.tag}</Chip>
                  {source.why === null ? null : (
                    <p className="m-0 text-[1rem] text-fg leading-[1.85]">
                      {T.sourceLine(source.why.relation_label, source.why.matched_on)}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        )}
        {why.limits.length === 0 ? null : (
          <Section title={T.limits}>
            <Items items={why.limits} />
          </Section>
        )}
        <Section title={T.personalisation}>
          <p className="m-0 text-[1rem] text-fg leading-[1.85]">
            {why.personalised_because === null
              ? T.notPersonalised
              : `${T.personalised} ${why.personalised_because}`}
          </p>
        </Section>
      </div>
    </Sheet>
  );
}
