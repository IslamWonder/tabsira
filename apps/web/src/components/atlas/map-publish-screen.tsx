'use client';

import type { Polygon } from 'geojson';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { signInHref } from '@/account/links';
import { myEntry, placeInsight, publishEntry, searchPlaces, withdrawEntry } from '@/atlas/api';
import type { LocationMeaning, LocationSource, MapEntryOwner, PlaceHit } from '@/atlas/types';
import { DEFAULT_VIEW, lngLatOf } from '@/atlas/types';
import { StatusScreen } from '@/components/app/status-screen';
import { IdentityForm } from '@/components/community/identity-section';
import { AtlasIcon } from '@/components/icons';
import { PageContainer } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { CheckboxField } from '@/components/ui/checkbox-field';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { TextField } from '@/components/ui/text-field';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { useKeptPhoto } from '@/lib/scan/kept-photo';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { entryPath } from './atlas-screen';
import { MapView } from './map-view';

const P = messages.atlas.publish;
const A = messages.atlas;
const C = messages.community;
const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;

interface Chosen {
  lngLat: [number, number];
  source: LocationSource;
  accuracy: number | null;
  measuredAt: string | null;
}

function problemMessage(failure: Failure): string {
  if (failure.code === 'INSIGHT_NOT_PUBLISHABLE') {
    return P.notPublishable;
  }
  if (failure.code === 'PUBLIC_IDENTITY_REQUIRED') {
    return P.identityFirst;
  }
  return failureMessage(failure);
}

function round(value: number): string {
  return value.toFixed(5);
}

/**
 * Adding an insight to the atlas (extension §2, §3, §10): the owner chooses
 * where the photo was taken (the device's position now, a place found by name,
 * or a tap on the map; never the current position assigned to an old photo by
 * itself), says what the point stands for, reviews the cell the map will show,
 * and publishes. The exact point is kept for the owner alone.
 */
export function MapPublishScreen() {
  const params = useSearchParams();
  const insightId = params.get('insight');
  const access = useAccess();
  const [existing, setExisting] = useState<'unknown' | 'none' | MapEntryOwner>('unknown');
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [meaning, setMeaning] = useState<LocationMeaning>('capture_point');
  // The photo is the owner's choice, off until ticked, and offered only when a photo is kept.
  const [photo, setPhoto] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<PlaceHit[] | null>(null);
  const validId = insightId !== null && PUBLIC_ID.test(insightId);
  const photoKept = useKeptPhoto(validId ? insightId : null, access === 'member');

  useEffect(() => {
    if (!validId || access !== 'member' || insightId === null) {
      return;
    }
    void myEntry(insightId).then((result) => {
      setExisting(result.ok ? result.data : 'none');
    });
  }, [validId, access, insightId]);

  const entry = typeof existing === 'object' ? existing : null;

  const run = async (
    call: () => Promise<Awaited<ReturnType<typeof placeInsight>>>,
    done: string
  ) => {
    setBusy(true);
    setFailure(null);
    const result = await call();
    setBusy(false);
    if (result.ok) {
      setExisting(result.data);
      setNotice(done);
    } else {
      setFailure(problemMessage(result));
    }
  };

  const useDevice = () => {
    setFailure(null);
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setFailure(A.nearMeUnavailable);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        setChosen({
          lngLat: [position.coords.longitude, position.coords.latitude],
          source: 'device_capture',
          accuracy: Math.round(position.coords.accuracy),
          measuredAt: new Date(position.timestamp).toISOString(),
        }),
      () => setFailure(A.nearMeDenied),
      { enableHighAccuracy: true, timeout: 15_000 }
    );
  };

  const search = async () => {
    const q = query.trim();
    if (q.length < 2) {
      return;
    }
    const result = await searchPlaces(q);
    setHits(result.ok ? result.data : []);
  };

  const save = () => {
    /* v8 ignore next: narrows the type; the button is disabled without a point and the form needs a valid id */
    if (chosen === null || insightId === null) {
      return;
    }
    void run(
      () =>
        placeInsight(insightId, {
          latitude: chosen.lngLat[1],
          longitude: chosen.lngLat[0],
          accuracy_m: chosen.accuracy,
          source: chosen.source,
          meaning,
          measured_at: chosen.measuredAt,
          photo: photoKept && photo,
        }),
      P.saved
    );
  };

  const withdraw = async () => {
    /* v8 ignore next: narrows the type; the sheet exists only under a valid id */
    if (insightId === null) {
      return;
    }
    setBusy(true);
    const result = await withdrawEntry(insightId);
    setBusy(false);
    setWithdrawing(false);
    if (result.ok) {
      setExisting('none');
      setChosen(null);
      setNotice(P.withdrawn);
    } else {
      setFailure(failureMessage(result));
    }
  };

  if (!validId) {
    return (
      <PageContainer className="pt-[max(28px,env(safe-area-inset-top))] pb-10">
        <StatusScreen
          icon={<AtlasIcon width="28" height="28" />}
          title={P.noInsight.title}
          description={P.noInsight.description}
          className="py-10"
        >
          <LinkButton href="/world" variant="secondary">
            {P.noInsight.world}
          </LinkButton>
        </StatusScreen>
      </PageContainer>
    );
  }

  // While choosing, the owner's own point; once placed, the public point: what the atlas will show.
  const marker = entry?.public ? lngLatOf(entry.public.point) : (chosen?.lngLat ?? null);
  const cell: Polygon | null = entry?.public?.cell
    ? { type: 'Polygon', coordinates: entry.public.cell.coordinates }
    : null;

  return (
    <PageContainer className="flex max-w-[48rem] flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-6 tablet:pb-10">
      <Link
        href="/atlas"
        className="inline-flex min-h-10 items-center self-start text-link underline-offset-4 hover:underline"
      >
        {A.entry.back}
      </Link>
      <header className="flex flex-col gap-2">
        <h1 className="m-0 font-bold font-display text-[2rem] text-gilded">{P.title}</h1>
        <p className="m-0 text-fg-soft leading-[1.85]">{P.lead}</p>
      </header>

      {access === 'guest' ? (
        <GlassPanel className="flex flex-col items-start gap-3">
          <p className="m-0 text-fg-soft">{P.signIn}</p>
          <LinkButton href={signInHref(`/atlas/publish?insight=${insightId}`)}>
            {C.signIn}
          </LinkButton>
        </GlassPanel>
      ) : null}
      {access === 'unverified' ? (
        <GlassPanel>
          <p className="m-0 text-fg-soft">{P.verify}</p>
        </GlassPanel>
      ) : null}
      {access === 'no-identity' ? (
        <GlassPanel as="section" aria-label={C.identity.title} className="flex flex-col gap-4">
          <p className="m-0 font-semibold text-fg text-lg">{P.identityFirst}</p>
          <IdentityForm />
        </GlassPanel>
      ) : null}
      {access === 'unknown' || (access === 'member' && existing === 'unknown') ? (
        <p role="status" className="m-0 text-fg-muted">
          {P.loadingMine}
        </p>
      ) : null}

      {access === 'member' && existing !== 'unknown' ? (
        <div className="flex flex-col gap-5">
          <div role="status" className="empty:hidden">
            {notice === null ? null : <Notice tone="success">{notice}</Notice>}
          </div>
          {entry === null || entry.status === 'withdrawn' ? (
            <GlassPanel ornate className="flex flex-col gap-5 tablet:p-7">
              <div className="flex flex-col gap-1">
                <h2 className="m-0 font-semibold text-[1.25rem] text-fg">{P.where}</h2>
                <p className="m-0 text-fg-muted text-sm leading-[1.8]">{P.whereHint}</p>
              </div>
              <div className="flex flex-col gap-2">
                <Button variant="secondary" onClick={useDevice} className="self-start">
                  {P.useDevice}
                </Button>
                <p className="m-0 text-[0.8125rem] text-fg-muted">{P.useDeviceHint}</p>
              </div>
              <form
                aria-label={A.searchForm}
                onSubmit={(event) => {
                  event.preventDefault();
                  void search();
                }}
                className="flex flex-col gap-2"
              >
                <div className="flex items-end gap-2">
                  <TextField
                    label={P.searchPlace}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    autoComplete="off"
                    className="min-w-0 flex-1"
                  />
                  <Button type="submit" variant="secondary">
                    {A.search}
                  </Button>
                </div>
                {hits === null ? null : hits.length === 0 ? (
                  <p role="status" className="m-0 text-fg-muted text-sm">
                    {A.noPlaces}
                  </p>
                ) : (
                  <ul className="m-0 flex list-none flex-col gap-1 p-0">
                    {hits.map((hit) => (
                      <li key={hit.geoname_id}>
                        <button
                          type="button"
                          onClick={() => {
                            setChosen({
                              lngLat: [hit.longitude, hit.latitude],
                              source: 'user_selected',
                              accuracy: null,
                              measuredAt: null,
                            });
                            setMeaning('public_place');
                            setHits(null);
                          }}
                          className="flex min-h-12 w-full items-center justify-between gap-3 rounded-[var(--radius-card)] px-3 text-start text-fg transition-colors duration-200 hover:bg-surface"
                        >
                          <span>{hit.label}</span>
                          <span className="text-[0.8125rem] text-fg-muted">
                            {A.joinLabels([hit.admin_area?.label, hit.country?.label])}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </form>
              <p className="m-0 text-fg-muted text-sm">{P.tapMap}</p>
              <div className="h-72 overflow-hidden rounded-[var(--radius-card)] border border-line">
                <MapView
                  marker={marker}
                  view={chosen === null ? DEFAULT_VIEW : { center: chosen.lngLat, zoom: 13 }}
                  onPick={(lngLat) =>
                    setChosen({ lngLat, source: 'user_selected', accuracy: null, measuredAt: null })
                  }
                />
              </div>
              <p role="status" className="m-0 text-fg-soft text-sm">
                {chosen === null
                  ? P.noLocation
                  : `${P.chosen}: ${round(chosen.lngLat[1])}, ${round(chosen.lngLat[0])}`}
              </p>
              <ChoiceGroup
                legend={P.meaning}
                options={(['capture_point', 'public_place'] as const).map((value) => ({
                  value,
                  label: P.meanings[value],
                }))}
                value={meaning}
                onChange={setMeaning}
              />
              {photoKept ? (
                <CheckboxField
                  label={P.photo}
                  hint={P.photoHint}
                  checked={photo}
                  onChange={setPhoto}
                />
              ) : null}
              {failure === null ? null : (
                <div role="alert">
                  <Notice tone="error">{failure}</Notice>
                </div>
              )}
              <Button
                size="lg"
                onClick={save}
                disabled={busy || chosen === null}
                className="self-start"
              >
                {busy ? P.saving : P.save}
              </Button>
            </GlassPanel>
          ) : (
            <GlassPanel ornate className="flex flex-col gap-5 tablet:p-7">
              <div className="flex flex-col gap-1">
                <h2 className="m-0 font-semibold text-[1.25rem] text-fg">{P.preview}</h2>
                <p className="m-0 text-fg-muted text-sm leading-[1.8]">{P.previewHint}</p>
              </div>
              <p className="m-0 text-[0.875rem] text-fg-soft">{P.status[entry.status]}</p>
              {entry.status_message === null ? null : (
                <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.75]">
                  {entry.status_message}
                </p>
              )}
              <div className="h-72 overflow-hidden rounded-[var(--radius-card)] border border-line">
                <MapView
                  marker={marker}
                  cell={cell}
                  view={
                    entry.public ? { center: lngLatOf(entry.public.point), zoom: 13 } : DEFAULT_VIEW
                  }
                  interactive={false}
                />
              </div>
              <dl className="m-0 flex flex-col gap-1 text-[0.9375rem]">
                <div className="flex gap-2">
                  <dt className="text-fg-muted">{P.precision}</dt>
                  <dd className="m-0 text-fg">{entry.public?.precision_label}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-fg-muted">{P.placeLabel}</dt>
                  <dd className="m-0 text-fg">
                    {entry.place === null
                      ? P.noPlace
                      : A.joinLabels([
                          entry.place.label,
                          entry.place.admin_label,
                          entry.place.country_label,
                        ])}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dd className="m-0 text-fg-soft">{entry.public?.meaning_label}</dd>
                </div>
                {entry.photo ? (
                  <div className="flex gap-2">
                    <dd className="m-0 text-fg-soft">{P.withPhoto}</dd>
                  </div>
                ) : null}
              </dl>
              {failure === null ? null : (
                <div role="alert">
                  <Notice tone="error">{failure}</Notice>
                </div>
              )}
              <div className="flex flex-wrap gap-2.5">
                {entry.status === 'pending_review' ||
                entry.status === 'removed' ? null : entry.status === 'draft' ? (
                  <Button
                    size="lg"
                    disabled={busy}
                    onClick={() => void run(() => publishEntry(entry.insight_id), P.published)}
                  >
                    {busy ? P.publishing : P.publish}
                  </Button>
                ) : (
                  <LinkButton href={entryPath(entry.id)} size="lg">
                    {P.open}
                  </LinkButton>
                )}
                <Button variant="secondary" size="lg" onClick={() => setExisting('none')}>
                  {P.where}
                </Button>
                <Button variant="ghost" size="lg" onClick={() => setWithdrawing(true)}>
                  {P.withdraw}
                </Button>
              </div>
            </GlassPanel>
          )}
          <Sheet
            open={withdrawing}
            onClose={() => setWithdrawing(false)}
            title={P.withdrawTitle}
            description={P.withdrawLead}
          >
            <div className="flex flex-wrap gap-2.5 pb-2">
              <Button onClick={() => void withdraw()} disabled={busy}>
                {busy ? P.withdrawing : P.withdrawConfirm}
              </Button>
              <Button variant="ghost" onClick={() => setWithdrawing(false)}>
                {P.cancel}
              </Button>
            </div>
          </Sheet>
        </div>
      ) : null}
    </PageContainer>
  );
}
