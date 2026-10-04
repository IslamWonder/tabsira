import { Chip } from '@/components/ui/chip';
import type { Insight } from '@/lib/scan/api';

/**
 * The platform's own explanation, apart from the two quoted texts and marked
 * as the API tags it (tajriba LUX-03: what is quoted and what is explained
 * never blur). what was seen is shown elsewhere, as what the photo shows; each
 * other part keeps the API's own label and wording.
 */
export function ExplanationSections({
  tag,
  parts,
}: {
  tag: string;
  parts: Insight['explanation'];
}) {
  const shown = parts.filter((part) => part.section !== 'seen');
  if (shown.length === 0) {
    return null;
  }
  return (
    <section aria-label={tag} className="flex flex-col items-start gap-3">
      <Chip tone="primary">{tag}</Chip>
      <dl className="m-0 flex flex-col gap-4">
        {shown.map((part) => (
          <div key={part.section} className="flex flex-col gap-1">
            <dt className="font-semibold text-[0.9375rem] text-fg-soft">{part.label}</dt>
            <dd className="m-0 text-[1.0625rem] text-fg leading-[1.9]">{part.text}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
