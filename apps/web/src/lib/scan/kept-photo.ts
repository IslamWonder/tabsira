'use client';

import { useEffect, useState } from 'react';
import { getInsight } from '@/lib/scan/api';

/**
 * Whether the owner's own copy of the insight's photo is kept (`image.has_photo`,
 * v2 §19), so a publish screen may offer to show it. Asked only for a signed-in
 * owner; any failure, and an insight without a kept photo, mean no offer at all.
 */
export function useKeptPhoto(insightId: string | null, enabled: boolean): boolean {
  const [kept, setKept] = useState(false);
  useEffect(() => {
    if (!enabled || insightId === null) {
      return;
    }
    let current = true;
    void getInsight(insightId).then((result) => {
      if (current) {
        setKept(result.ok && result.data.image.has_photo);
      }
    });
    return () => {
      current = false;
    };
  }, [insightId, enabled]);
  return kept;
}
