'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { pauseClarity, startClarity, stopClarity } from '@/analytics/clarity';
import { dropQueuedEvents, track } from '@/analytics/events';
import {
  pauseGoogleAnalytics,
  setGooglePageTitle,
  startGoogleAnalytics,
  stopGoogleAnalytics,
} from '@/analytics/google';
import { isExcludedPath, isHeatmapExcludedPath } from '@/analytics/paths';
import { ConsentGate } from '@/consent/consent-gate';
import { useConsent } from '@/consent/store';

export interface AnalyticsTagsProps {
  /** GA_MEASUREMENT_ID, read on the server at request time; null means no Google code at all. */
  gaId: string | null;
  /** CLARITY_PROJECT_ID, read the same way; null means no heatmaps. */
  clarityId: string | null;
}

/** Runs while the analytics category is accepted; unmounting is the withdrawal. */
function GoogleAnalytics({ id }: { id: string }) {
  const pathname = usePathname();
  const allowed = !isExcludedPath(pathname);
  useEffect(
    () => () => {
      stopGoogleAnalytics(id);
      dropQueuedEvents();
    },
    [id]
  );
  useEffect(() => {
    if (allowed) {
      // Before the start, so the first page view carries it too, and again on every path change.
      setGooglePageTitle(pathname);
      startGoogleAnalytics(id, pathname);
    } else {
      pauseGoogleAnalytics(id);
    }
  }, [id, allowed, pathname]);
  return null;
}

/** Runs while the behaviour category is accepted; unmounting is the withdrawal. */
function Heatmaps({ id }: { id: string }) {
  const allowed = !isHeatmapExcludedPath(usePathname());
  useEffect(() => () => stopClarity(), []);
  useEffect(() => {
    if (allowed) {
      startClarity(id);
    } else {
      pauseClarity();
    }
  }, [id, allowed]);
  return null;
}

/** Reports a change of the choice, once, and not the choice a returning visitor already had. */
function ConsentChangedEvent() {
  const { consent } = useConsent();
  const previous = useRef<string | null>(null);
  useEffect(() => {
    if (consent.status === 'unknown' || consent.status === 'checking') {
      return;
    }
    if (consent.status !== 'decided') {
      previous.current ??= consent.status;
      return;
    }
    const { analytics, behaviour } = consent.record.categories;
    const key = `${analytics}:${behaviour}`;
    if (previous.current !== null && previous.current !== key) {
      track('consent_changed', { analytics, behaviour });
    }
    previous.current = key;
  }, [consent]);
  return null;
}

/**
 * The analytics tools, each behind its own category (owner decisions 28, 31
 * and 32). Without consent this renders nothing and no request is made.
 */
export function AnalyticsTags({ gaId, clarityId }: AnalyticsTagsProps) {
  return (
    <>
      {gaId === null ? null : (
        <ConsentGate category="analytics">
          <GoogleAnalytics id={gaId} />
        </ConsentGate>
      )}
      {clarityId === null ? null : (
        <ConsentGate category="behaviour">
          <Heatmaps id={clarityId} />
        </ConsentGate>
      )}
      {gaId === null ? null : <ConsentChangedEvent />}
    </>
  );
}
