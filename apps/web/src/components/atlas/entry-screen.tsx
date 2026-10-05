'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useSession } from '@/account/session';
import { getEntry } from '@/atlas/api';
import type { AtlasEntry } from '@/atlas/types';
import { EMPTY_FILTERS, lngLatOf } from '@/atlas/types';
import { atlasHref } from '@/atlas/view-state';
import { StatusScreen } from '@/components/app/status-screen';
import { PostEvidence } from '@/components/community/evidence';
import { PublicPhoto } from '@/components/community/public-photo';
import { ReportSheet } from '@/components/community/sheets';
import { AtlasIcon } from '@/components/icons';
import { PageContainer } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import { postPath, profilePath } from '@/social/identity';
import { placePath } from './atlas-screen';
import { MapView } from './map-view';

const A = messages.atlas;

type Load =
  | { kind: 'loading' }
  | { kind: 'ready'; entry: AtlasEntry }
  | { kind: 'gone' }
  | { kind: 'missing' }
  | { kind: 'failed'; failure: Failure };

/**
 * One entry of the atlas on its own page: the insight by reference with its
 * scripture exactly as the API returns it, the approximate point on a small
 * map with the note that it is approximate, the place, and the author.
 */
export function EntryScreen({ entryId }: { entryId: string }) {
  const session = useSession();
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [reporting, setReporting] = useState(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` counts the retries; each one asks again.
  useEffect(() => {
    let current = true;
    setLoad({ kind: 'loading' });
    void getEntry(entryId).then((result) => {
      if (!current) {
        return;
      }
      if (result.ok) {
        setLoad({ kind: 'ready', entry: result.data });
      } else if (result.status === 410) {
        setLoad({ kind: 'gone' });
      } else if (result.status === 404) {
        setLoad({ kind: 'missing' });
      } else {
        setLoad({ kind: 'failed', failure: result });
      }
    });
    return () => {
      current = false;
    };
  }, [entryId, attempt]);

  return (
    <PageContainer className="flex max-w-[48rem] flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-6 tablet:pb-10">
      <Link
        href="/atlas"
        className="inline-flex min-h-10 items-center self-start text-link underline-offset-4 hover:underline"
      >
        {A.entry.back}
      </Link>
      {load.kind === 'loading' ? (
        <p role="status" className="m-0 py-8 text-center text-fg-muted">
          {A.loading}
        </p>
      ) : null}
      {load.kind === 'ready' ? (
        <>
          <GlassPanel
            as="article"
            ornate
            className="flex flex-col gap-5 tablet:p-7"
            aria-label={load.entry.title}
          >
            <header className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-fg-muted">
                <Chip>{load.entry.location.precision_label}</Chip>
                <Chip>{load.entry.location.meaning_label}</Chip>
                <time dateTime={load.entry.published_on}>
                  {A.card.publishedAt(formatDay(load.entry.published_on))}
                </time>
              </div>
              <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
                {load.entry.title}
              </h1>
              <p className="m-0 text-[1.0625rem] text-fg-soft leading-[1.85]">
                {load.entry.glimpse}
              </p>
              <p className="m-0 text-[0.875rem] text-fg-muted">
                {load.entry.author === null ? null : (
                  <>
                    {A.card.by('')}
                    <Link
                      href={profilePath(load.entry.author.handle)}
                      className="text-link underline-offset-4 hover:underline"
                    >
                      {load.entry.author.public_name}
                    </Link>
                  </>
                )}
                {load.entry.place === null ? null : (
                  <>
                    {load.entry.author === null ? null : ' · '}
                    <Link
                      href={placePath(load.entry.place.geoname_id)}
                      className="text-link underline-offset-4 hover:underline"
                    >
                      {A.joinLabels([load.entry.place.label, load.entry.place.country_label])}
                    </Link>
                  </>
                )}
              </p>
            </header>
            <PublicPhoto url={load.entry.photo_url} alt={A.entry.photoAlt(load.entry.title)} />
            <section aria-label={A.entry.mapLabel} className="flex flex-col gap-2">
              <div className="h-56 overflow-hidden rounded-[var(--radius-card)] border border-line">
                <MapView
                  interactive={false}
                  marker={lngLatOf(load.entry.location.point)}
                  view={{ center: lngLatOf(load.entry.location.point), zoom: 10 }}
                />
              </div>
              <p className="m-0 text-[0.8125rem] text-fg-muted leading-[1.8]">
                {A.entry.locationNote}
              </p>
            </section>
            <section aria-label={A.entry.explanation} className="flex flex-col items-start gap-2">
              <Chip tone="primary">{A.entry.explanation}</Chip>
              <p className="m-0 text-fg leading-[1.9]">{load.entry.explanation}</p>
            </section>
            <PostEvidence insight={load.entry} headingLevel={2} />
            {load.entry.step === null ? null : (
              <p className="m-0 rounded-[var(--radius-card)] border border-[var(--step-border)] bg-[linear-gradient(135deg,var(--step-surface-from),var(--step-surface-to))] px-4 py-3 text-[0.9375rem] text-fg leading-[1.8]">
                <strong className="font-semibold text-step-title">{A.entry.step}</strong> ·{' '}
                {load.entry.step}
              </p>
            )}
            <footer className="flex flex-wrap items-center gap-2.5 border-line border-t pt-4">
              {load.entry.concepts[0] === undefined ? null : (
                <LinkButton
                  href={atlasHref({
                    view: null,
                    selected: null,
                    filters: { ...EMPTY_FILTERS, concept: load.entry.concepts[0] },
                  })}
                  variant="secondary"
                >
                  {A.entry.sameMeaning}
                </LinkButton>
              )}
              {load.entry.post_id === null ? null : (
                <LinkButton href={postPath(load.entry.post_id)} variant="secondary">
                  {A.card.openPost}
                </LinkButton>
              )}
              {session.status === 'signed-in' ? (
                <Button variant="ghost" onClick={() => setReporting(true)}>
                  {messages.community.report.action}
                </Button>
              ) : null}
            </footer>
          </GlassPanel>
          <ReportSheet
            open={reporting}
            onClose={() => setReporting(false)}
            targetType="map_entry"
            targetId={load.entry.id}
          />
        </>
      ) : null}
      {load.kind === 'gone' || load.kind === 'missing' ? (
        <StatusScreen
          icon={<AtlasIcon width="28" height="28" />}
          title={load.kind === 'gone' ? A.entry.gone.title : A.entry.notFound.title}
          description={
            load.kind === 'gone' ? A.entry.gone.description : A.entry.notFound.description
          }
          className="py-10"
        >
          <LinkButton href="/atlas" variant="secondary">
            {A.entry.back}
          </LinkButton>
        </StatusScreen>
      ) : null}
      {load.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{failureMessage(load.failure)}</Notice>
          <Button variant="ghost" onClick={() => setAttempt((count) => count + 1)}>
            {A.retry}
          </Button>
        </div>
      ) : null}
    </PageContainer>
  );
}
