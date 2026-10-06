'use client';

import { useRef, useState } from 'react';
import { publicInsightPath } from '@/lib/public-insight';
import { shareLink } from '@/lib/share-link';
import { publishInsight } from './publication';
import { addressOf, refusal } from './share-sheet';

export interface QuickShareSaid {
  tone: 'success' | 'info' | 'error';
  text: string;
}

export interface QuickShare {
  /** Whether the insight is public now: what this screen did, else what the server said on load. */
  published: boolean;
  setPublished: (published: boolean) => void;
  working: boolean;
  said: QuickShareSaid | null;
  /** One tap: publish if needed and open the system share dialog with the public address. */
  run: () => void;
}

/**
 * Sharing in one tap. The public address is known before publishing (it is
 * `/insights/<id>`, the path the API names), so the system's share call is made
 * at once, inside the tap, while the publication runs beside it: awaiting the
 * network first would spend the tap's permission and iOS would refuse the dialog.
 * If the publication is then refused, the API's reason is said, so the owner knows
 * the link will not open.
 */
export function useQuickShare(
  insightId: string,
  title: string,
  initiallyPublished: boolean
): QuickShare {
  const [publishedHere, setPublishedHere] = useState<boolean | null>(null);
  const published = publishedHere ?? initiallyPublished;
  const [working, setWorking] = useState(false);
  const [said, setSaid] = useState<QuickShareSaid | null>(null);
  // A state update lands after a second tap could already have run; a ref closes that gap.
  const busy = useRef(false);

  const run = () => {
    if (busy.current) {
      return;
    }
    busy.current = true;
    setWorking(true);
    setSaid(null);
    const sharing = shareLink(title, addressOf(publicInsightPath(insightId)), title);
    const publishing = published ? Promise.resolve(null) : publishInsight(insightId);
    void Promise.all([sharing, publishing]).then(([shared, result]) => {
      if (result !== null && !result.ok) {
        setSaid({ tone: 'error', text: refusal(result) });
      } else {
        if (result !== null) {
          setPublishedHere(true);
        }
        setSaid(shared);
      }
      busy.current = false;
      setWorking(false);
    });
  };

  return { published, setPublished: setPublishedHere, working, said, run };
}
