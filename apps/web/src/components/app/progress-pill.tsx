'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { SparkIcon } from '@/components/icons';
import { getProgress } from '@/lib/scan/api';
import { messages } from '@/messages';

const P = messages.nav.progress;

interface Summary {
  insights: number;
  streak: number;
}

/** The reader's time zone, for what «today» means in the streak; UTC where it cannot be read. */
function timeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/**
 * A quiet count in the top bar: the insights completed and the days in a
 * row, leading to the practice page. Practice, never piety (decision 27): no
 * comparison, no reward, nothing said about a missed day. Read again on every
 * page, so it follows a new completion; absent before the first one and whenever
 * the API does not answer.
 */
export function ProgressPill() {
  const pathname = usePathname();
  const [summary, setSummary] = useState<Summary | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: read again on each new page.
  useEffect(() => {
    let current = true;
    void getProgress(timeZone()).then((result) => {
      if (current && result.ok) {
        setSummary({
          insights: result.data.counts.completed,
          streak: result.data.streak.current,
        });
      }
    });
    return () => {
      current = false;
    };
  }, [pathname]);

  if (summary === null || summary.insights === 0) {
    return null;
  }
  return (
    <Link
      href="/sky"
      aria-label={P.label(summary.insights, summary.streak)}
      className="inline-flex min-h-10 items-center gap-2 whitespace-nowrap rounded-full border border-line px-3 text-glass-fg-soft text-sm transition-colors duration-200 hover:text-glass-fg"
    >
      <SparkIcon width="16" height="16" aria-hidden="true" className="text-[var(--ornament)]" />
      <span>{P.insights(summary.insights)}</span>
      {summary.streak > 0 ? (
        <span className="hidden desktop:inline">· {P.streak(summary.streak)}</span>
      ) : null}
    </Link>
  );
}
