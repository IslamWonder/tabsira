import Link from 'next/link';
import type { CommunitySummary as Summary } from '@/lib/community-summary';
import { messages } from '@/messages';

const M = messages.landing.community;

/** Figures in Arabic-Indic digits, as the other display counts (components/fx/count-up.tsx). */
const FORMAT = new Intl.NumberFormat('ar-u-nu-arab');

interface Figure {
  key: string;
  label: string;
  value: number;
  note?: string;
}

function figures(summary: Summary): Figure[] {
  const list: Figure[] = [
    {
      key: 'members',
      label: M.members,
      value: summary.members,
      ...(summary.countries
        ? { note: M.fromCountries(summary.countries, FORMAT.format(summary.countries)) }
        : {}),
    },
  ];
  // A figure whose feature is switched off is null and is left out.
  if (summary.insights !== null) {
    list.push({ key: 'insights', label: M.insights, value: summary.insights });
  }
  if (summary.atlas_entries !== null) {
    list.push({ key: 'atlas', label: M.atlas, value: summary.atlas_entries });
  }
  if (summary.sponsorships_open) {
    list.push({ key: 'sponsorships', label: M.sponsorships, value: summary.sponsorships_open });
  }
  return list;
}

function onward(summary: Summary): { href: '/community' | '/atlas'; label: string } | null {
  if (summary.insights !== null) {
    return { href: '/community', label: M.toCommunity };
  }
  return summary.atlas_entries === null ? null : { href: '/atlas', label: M.toAtlas };
}

/**
 * A quiet card of public counts, below the way in so it never competes with the capture
 * (decision 62). Rendered on the server; each figure is text, its label read before it.
 * Nothing moves: no count-up, no hover motion.
 */
export function CommunitySummary({ summary }: Readonly<{ summary: Summary }>) {
  const link = onward(summary);
  return (
    <section
      aria-labelledby="landing-community"
      className="mx-auto w-full max-w-[1200px] px-4 tablet:px-7 desktop:px-6 wide:max-w-[1240px]"
    >
      <div className="flex flex-col gap-5 rounded-[18px] border border-line bg-surface p-5 tablet:p-6">
        <div className="flex flex-col gap-1">
          <h2 id="landing-community" className="m-0 font-semibold text-fg text-subheading">
            {M.title}
          </h2>
          <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.8]">{M.lead}</p>
        </div>
        <dl className="m-0 grid grid-cols-2 gap-4 tablet:grid-cols-4">
          {figures(summary).map((figure) => (
            <div key={figure.key} className="flex flex-col gap-0.5">
              <dt className="order-2 text-[0.875rem] text-fg-soft">{figure.label}</dt>
              <dd className="order-1 m-0 font-bold font-display text-[1.75rem] text-[var(--landing-gold)] leading-[1.3]">
                {FORMAT.format(figure.value)}
              </dd>
              {figure.note === undefined ? null : (
                <dd className="order-3 m-0 text-[0.8125rem] text-fg-muted">{figure.note}</dd>
              )}
            </div>
          ))}
        </dl>
        {link === null ? null : (
          <Link
            href={link.href}
            className="inline-flex min-h-12 items-center self-start font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-2"
          >
            {link.label}
          </Link>
        )}
      </div>
    </section>
  );
}
