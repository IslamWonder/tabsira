'use client';

import { useRef, useState } from 'react';
import type { Result } from '@/lib/api/result';
import { publicInsightPath } from '@/lib/public-insight';
import { shareLink } from '@/lib/share-link';
import { type InsightPost, publishInsight, publishPost } from './publication';
import { addressOf, postNote, refusal } from './share-sheet';

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
  /**
   * One tap: publish if needed, open the system share dialog with the public address, and put
   * the insight in the owner's publications in the network (decision 68).
   */
  run: () => void;
}

/**
 * Sharing in one tap. The public address is known before publishing (it is
 * `/insights/<id>`, the path the API names), so the system's share call is made
 * at once, inside the tap, while the publication runs beside it: awaiting the
 * network first would spend the tap's permission and iOS would refuse the dialog.
 * If the publication is then refused, the API's reason is said, so the owner knows
 * the link will not open. Beside it the insight's post is published (decision 68), so a
 * shared basira is in the owner's publications; without a public handle yet, the owner is
 * told where to choose one. `community` is whether the network's feature is on.
 */
export function useQuickShare(
  insightId: string,
  title: string,
  initiallyPublished: boolean,
  community = false
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
    // Only with the page's own publication: a post the owner withdrew is never made again by a
    // later share of a page that is already public.
    const posting: Promise<Result<InsightPost> | null> =
      community && !published ? publishPost(insightId) : Promise.resolve(null);
    void Promise.all([sharing, publishing, posting]).then(([shared, result, post]) => {
      if (result !== null && !result.ok) {
        setSaid({ tone: 'error', text: refusal(result) });
      } else {
        if (result !== null) {
          setPublishedHere(true);
        }
        setSaid(postNote(post) ?? shared);
      }
      busy.current = false;
      setWorking(false);
    });
  };

  return { published, setPublished: setPublishedHere, working, said, run };
}
