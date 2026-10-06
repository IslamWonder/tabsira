'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { entriesIn } from '@/atlas/api';
import {
  bearingDegrees,
  distanceMeters,
  inView,
  type LngLat,
  RADIUS_MAX_M,
  refetchDistance,
  relativeAngle,
  roundedDistance,
  type Sector,
  searchRadius,
  sectorOf,
  windowAround,
} from '@/atlas/geo';
import { type AtlasFeature, EMPTY_FILTERS, lngLatOf, type PlaceHit } from '@/atlas/types';
import { atlasHref, zoomForRadius } from '@/atlas/view-state';
import { AtlasIcon, CameraIcon } from '@/components/icons';
import { StageLayout } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { PlaceSearch } from './atlas-screen';
import { useCameraStream, useDeviceHeading, useDevicePosition } from './camera-sensors';
import { OrphansSection } from './orphans-section';
import { entryPath } from './paths';

const A = messages.atlas;
const C = messages.atlas.camera;

/** At most this many labels over the view (extension §5.4); the rest wait in the list. */
export const OVERLAY_MAX = 5;
/** A fix looser than this says only which area the device is in: level A, no arrows. */
export const DIRECTION_MAX_ACCURACY_M = 500;

type Load =
  | { kind: 'idle' | 'loading' }
  | { kind: 'ready'; truncated: boolean }
  | { kind: 'failed'; message: string };

/** The centre of the exploration: the device, or a place the reader chose when the device gave none. */
type Centre = { kind: 'device'; point: LngLat; accuracyM: number | null } | ChosenCentre;
type ChosenCentre = { kind: 'chosen'; point: LngLat; label: string };

interface Item {
  feature: AtlasFeature;
  distanceM: number;
  bearing: number;
}

interface Shown extends Item {
  /** The distance to show, or null inside the entry's own cell. */
  roundedM: number | null;
  /** The turn from the camera to the entry's area, when the heading is known and the entry is beyond its cell. */
  relative: number | null;
  sector: Sector | null;
  inView: boolean;
}

export type Mode = 'area' | 'direction' | 'chosen';

function distanceText(roundedM: number | null): string {
  if (roundedM === null) {
    return C.near;
  }
  if (roundedM < 1000) {
    return C.about(C.meters(roundedM));
  }
  const km = roundedM / 1000;
  return C.about(C.kilometers(Number.isInteger(km) ? String(km) : km.toFixed(1)));
}

/** A short arrow, turned toward the entry's area; the words beside it carry the meaning. */
function Arrow({ relative, sector }: Readonly<{ relative: number; sector: Sector }>) {
  return (
    <svg
      role="img"
      aria-label={C.arrow(C.sectors[sector])}
      viewBox="0 0 24 24"
      width="28"
      height="28"
      className="shrink-0 text-primary motion-safe:transition-transform motion-safe:duration-200"
      style={{ transform: `rotate(${Math.round(relative)}deg)` }}
    >
      <path
        d="M12 3l6 9h-4v9h-4v-9H6z"
        fill="currentColor"
        stroke="currentColor"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** One entry's line: its distance or area, and its direction when known. */
function Whereabouts({ shown, mode }: Readonly<{ shown: Shown; mode: Mode }>) {
  if (mode === 'chosen') {
    return <span className="text-[0.8125rem] text-fg-muted">{C.inArea}</span>;
  }
  return (
    <span className="flex items-center gap-2 text-[0.8125rem] text-fg-muted">
      <span>{distanceText(shown.roundedM)}</span>
      {shown.relative !== null && shown.sector !== null ? (
        <>
          <Arrow relative={shown.relative} sector={shown.sector} />
          <span>{C.toward(C.sectors[shown.sector])}</span>
          {shown.inView ? <Chip tone="primary">{C.inViewMark}</Chip> : null}
        </>
      ) : null}
    </span>
  );
}

function Label({ shown, mode }: Readonly<{ shown: Shown; mode: Mode }>) {
  const { properties } = shown.feature;
  return (
    <Link
      href={entryPath(shown.feature.id)}
      tabIndex={-1}
      className="glass flex min-h-12 flex-col gap-0.5 rounded-[18px] px-4 py-2.5 text-start text-glass-fg"
    >
      <span className="font-semibold">{properties.title}</span>
      <span className="text-[0.8125rem] text-glass-fg-soft">
        {A.joinLabels([
          properties.place?.label,
          mode === 'chosen' ? null : distanceText(shown.roundedM),
          shown.sector === null ? null : C.sectors[shown.sector],
        ])}
      </span>
    </Link>
  );
}

/**
 * The camera discovery, levels A and B (extension §5–7). The camera is shown
 * and never read; the position stays on the device and the atlas is asked for
 * a widened window around it, as the map is asked for the window it shows; the
 * entries are then measured and sorted here. A heading, when the sensors give
 * one anchored to north, adds a turn toward each entry's area, never toward a
 * thing. The list in the panel is the same knowledge for keyboards and screen
 * readers; nothing on the view is the only way to reach an entry. With the
 * sponsoring feature on, the orphaned entries around the same centre are offered
 * below, asked of the API with the centre snapped to the atlas grid.
 */
export function CameraScreen({ sponsorship = false }: Readonly<{ sponsorship?: boolean }>) {
  const camera = useCameraStream();
  const position = useDevicePosition();
  const heading = useDeviceHeading();
  const [phase, setPhase] = useState<'intro' | 'exploring'>('intro');
  const [chosen, setChosen] = useState<ChosenCentre | null>(null);
  const [widened, setWidened] = useState(0);
  const [features, setFeatures] = useState<AtlasFeature[]>([]);
  const [load, setLoad] = useState<Load>({ kind: 'idle' });
  const [showAll, setShowAll] = useState(false);
  const fetched = useRef<{ point: LngLat; radiusM: number } | null>(null);
  const latest = useRef(0);
  const viewed = useRef(new Map<string, boolean>());

  const centre: Centre | null =
    chosen ??
    (position.fix === null
      ? null
      : { kind: 'device', point: position.fix.center, accuracyM: position.fix.accuracyM });
  const radiusM = searchRadius(centre?.kind === 'device' ? centre.accuracyM : null, widened);

  const fetchAround = useCallback(async (point: LngLat, radius: number) => {
    const mine = ++latest.current;
    setLoad({ kind: 'loading' });
    const result = await entriesIn(windowAround(point, radius), EMPTY_FILTERS);
    if (mine !== latest.current) {
      return;
    }
    if (result.ok) {
      setFeatures(result.data.features);
      setLoad({ kind: 'ready', truncated: result.data.truncated });
    } else {
      setLoad({ kind: 'failed', message: failureMessage(result) });
    }
  }, []);

  // Ask again after a real move, a wider radius or a new centre, never on every reading.
  useEffect(() => {
    if (centre === null) {
      return;
    }
    const last = fetched.current;
    if (
      last !== null &&
      last.radiusM === radiusM &&
      distanceMeters(last.point, centre.point) < refetchDistance(radiusM)
    ) {
      return;
    }
    fetched.current = { point: centre.point, radiusM };
    void fetchAround(centre.point, radiusM);
  }, [centre, radiusM, fetchAround]);

  const retry = () => {
    /* v8 ignore next: narrows the type; a request fails only once a centre asked for it */
    if (centre !== null) {
      void fetchAround(centre.point, radiusM);
    }
  };

  const start = async () => {
    setPhase('exploring');
    await camera.start();
    position.start();
  };

  const lowAccuracy =
    centre?.kind === 'device' &&
    centre.accuracyM !== null &&
    centre.accuracyM > DIRECTION_MAX_ACCURACY_M;
  const mode: Mode =
    centre?.kind === 'chosen'
      ? 'chosen'
      : heading.state === 'ready' && heading.heading !== null && !lowAccuracy
        ? 'direction'
        : 'area';

  const items: Shown[] = useMemo(() => {
    if (centre === null) {
      return [];
    }
    const measured: Item[] = features
      .map((feature) => {
        const point = lngLatOf(feature.geometry);
        return {
          feature,
          distanceM: distanceMeters(centre.point, point),
          bearing: bearingDegrees(centre.point, point),
        };
      })
      .filter((item) => item.distanceM <= radiusM)
      .sort((a, b) => a.distanceM - b.distanceM);
    const seen = new Set<string>();
    const shown = measured.map((item): Shown => {
      seen.add(item.feature.id);
      const roundedM = roundedDistance(item.distanceM, item.feature.properties.cell_m);
      if (mode !== 'direction' || heading.heading === null || roundedM === null) {
        viewed.current.set(item.feature.id, false);
        return { ...item, roundedM, relative: null, sector: null, inView: false };
      }
      const relative = relativeAngle(item.bearing, heading.heading);
      const now = inView(viewed.current.get(item.feature.id) ?? false, relative);
      viewed.current.set(item.feature.id, now);
      return { ...item, roundedM, relative, sector: sectorOf(relative), inView: now };
    });
    for (const id of viewed.current.keys()) {
      if (!seen.has(id)) {
        viewed.current.delete(id);
      }
    }
    return shown;
  }, [centre, features, radiusM, mode, heading.heading]);

  const canWiden = radiusM < RADIUS_MAX_M;
  const listed = showAll ? items : items.slice(0, OVERLAY_MAX);
  // The atlas opens on the same view: this centre and radius, the nearest entry selected (extension §4).
  const mapHref =
    centre === null
      ? atlasHref({ view: null, selected: null, filters: EMPTY_FILTERS })
      : atlasHref({
          view: {
            center: [centre.point[0], centre.point[1]],
            zoom: zoomForRadius(radiusM, centre.point[1]),
          },
          selected: items[0]?.feature.id ?? null,
          filters: EMPTY_FILTERS,
        });

  const status = (() => {
    if (phase === 'intro') {
      return null;
    }
    if (centre === null) {
      if (position.state === 'denied') {
        return C.locationDenied;
      }
      if (position.state === 'unavailable') {
        return C.locationUnavailable;
      }
      return C.locating;
    }
    if (mode === 'chosen') {
      return `${C.mode.chosen}: ${(centre as ChosenCentre).label}`;
    }
    if (lowAccuracy) {
      return C.lowAccuracy;
    }
    if (mode === 'direction') {
      return C.mode.direction;
    }
    const byHeading: Partial<Record<typeof heading.state, string>> = {
      denied: C.headingDenied,
      unavailable: C.headingUnavailable,
      stale: C.headingStale,
      waiting: C.headingWaiting,
    };
    return byHeading[heading.state] ?? C.mode.area;
  })();

  const cameraNote = (() => {
    switch (camera.state) {
      case 'denied':
        return C.cameraDenied;
      case 'unavailable':
        return C.cameraUnavailable;
      case 'paused':
        return C.cameraPaused;
      default:
        return null;
    }
  })();

  const needsRegion =
    centre === null && (position.state === 'denied' || position.state === 'unavailable');

  const panel = (
    <div className="flex flex-col gap-5 px-4 py-6 tablet:px-0">
      <header className="flex flex-col gap-1.5">
        <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
          {C.title}
        </h1>
        <p className="m-0 text-fg-soft leading-[1.85]">{C.lead}</p>
      </header>
      {phase === 'intro' ? (
        <GlassPanel
          as="section"
          ornate
          aria-label={C.needs.heading}
          className="flex flex-col gap-4"
        >
          <h2 className="m-0 font-semibold text-lg text-fg">{C.needs.heading}</h2>
          <ul className="m-0 flex list-disc flex-col gap-2 ps-5 text-fg-soft leading-[1.85]">
            <li>{C.needs.camera}</li>
            <li>{C.needs.location}</li>
            <li>{C.needs.direction}</li>
          </ul>
          <p className="m-0 text-[0.875rem] text-fg-muted">{C.notLive}</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => void start()} className="gap-2">
              <CameraIcon width="20" height="20" aria-hidden="true" />
              {C.start}
            </Button>
            <LinkButton href="/atlas" variant="ghost">
              {C.showOnMap}
            </LinkButton>
          </div>
        </GlassPanel>
      ) : (
        <>
          <p role="status" aria-label={C.statusLabel} className="m-0 text-fg-soft text-sm">
            {camera.state === 'starting' ? C.starting : status}
          </p>
          {cameraNote === null ? null : (
            <div className="flex flex-wrap items-center gap-3">
              <Notice tone="info" className="flex-1">
                {cameraNote}
              </Notice>
              {camera.state === 'paused' ? (
                <Button variant="secondary" onClick={() => void camera.start()}>
                  {C.resumeCamera}
                </Button>
              ) : null}
            </div>
          )}
          {needsRegion ? (
            <PlaceSearch
              onPick={(hit: PlaceHit) =>
                setChosen({
                  kind: 'chosen',
                  point: [hit.longitude, hit.latitude],
                  label: hit.label,
                })
              }
            />
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {centre?.kind === 'device' && heading.state === 'idle' ? (
              <Button variant="secondary" onClick={() => void heading.enable()}>
                {C.enableHeading}
              </Button>
            ) : null}
            {camera.state === 'live' ? (
              <Button variant="ghost" onClick={camera.stop}>
                {C.stopCamera}
              </Button>
            ) : null}
            <LinkButton href={mapHref} variant="ghost">
              {C.showOnMap}
            </LinkButton>
          </div>
          {mode === 'direction' ? (
            <p className="m-0 text-[0.8125rem] text-fg-muted">{C.headingNote}</p>
          ) : null}
          <section aria-label={C.list} className="flex flex-col gap-3">
            <h2 className="m-0 flex items-baseline justify-between font-semibold text-lg text-fg">
              <span>{C.listHeading}</span>
              <span className="text-[0.875rem] text-fg-muted">{A.count(items.length)}</span>
            </h2>
            {load.kind === 'loading' ? (
              <p role="status" className="m-0 text-fg-muted">
                {C.loading}
              </p>
            ) : null}
            {load.kind === 'failed' ? (
              <div role="alert" className="flex flex-col items-start gap-3">
                <Notice tone="error">{load.message}</Notice>
                <Button variant="ghost" onClick={retry}>
                  {C.retry}
                </Button>
              </div>
            ) : null}
            {load.kind === 'ready' && items.length === 0 ? (
              <div className="flex flex-col items-start gap-3">
                <p role="status" className="m-0 text-fg-soft leading-[1.85]">
                  {C.empty} {C.emptyHint}
                </p>
                <div className="flex flex-wrap gap-2">
                  <LinkButton href="/atlas/publish" variant="secondary">
                    {C.addOwn}
                  </LinkButton>
                  {canWiden ? (
                    <Button variant="secondary" onClick={() => setWidened((n) => n + 1)}>
                      {C.widen}
                    </Button>
                  ) : (
                    <p className="m-0 self-center text-fg-muted text-sm">{C.widest}</p>
                  )}
                </div>
              </div>
            ) : null}
            {load.kind === 'ready' && load.truncated ? (
              <p className="m-0 text-fg-muted text-sm">{A.truncated}</p>
            ) : null}
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {listed.map((shown) => (
                <li key={shown.feature.id}>
                  <Link
                    href={entryPath(shown.feature.id)}
                    className="flex min-h-12 w-full flex-col items-start gap-0.5 rounded-[var(--radius-card)] px-3 py-2 text-start transition-colors duration-200 hover:bg-surface"
                  >
                    <span className="font-semibold text-fg">{shown.feature.properties.title}</span>
                    <span className="text-[0.8125rem] text-fg-muted">
                      {shown.feature.properties.place?.label ??
                        shown.feature.properties.precision_label}
                    </span>
                    <Whereabouts shown={shown} mode={mode} />
                  </Link>
                </li>
              ))}
            </ul>
            {items.length > OVERLAY_MAX ? (
              <Button
                variant="ghost"
                onClick={() => setShowAll((value) => !value)}
                aria-expanded={showAll}
                className="self-start"
              >
                {showAll ? C.showNearest : C.showAll(items.length)}
              </Button>
            ) : null}
            {load.kind === 'ready' && items.length > 0 && canWiden ? (
              <Button
                variant="ghost"
                onClick={() => setWidened((n) => n + 1)}
                className="self-start"
              >
                {C.widen}
              </Button>
            ) : null}
          </section>
          {sponsorship ? <OrphansSection point={centre?.point ?? null} /> : null}
          <p className="m-0 text-[0.8125rem] text-fg-muted">{C.notLive}</p>
        </>
      )}
    </div>
  );

  const stage = (
    <div className="relative h-full w-full bg-canvas">
      {/* The live view is decoration behind the labels: not read, not drawn, not described. */}
      <div aria-hidden="true" className={cx('h-full w-full', camera.state !== 'live' && 'hidden')}>
        <video
          ref={camera.videoRef}
          playsInline
          muted
          autoPlay
          className="h-full w-full object-cover"
        />
      </div>
      {camera.state === 'live' ? null : (
        <div
          aria-hidden="true"
          className="stage-aurora flex h-full w-full items-center justify-center text-fg-muted"
        >
          {phase === 'intro' ? (
            <CameraIcon width="56" height="56" />
          ) : (
            <AtlasIcon width="56" height="56" />
          )}
        </div>
      )}
      {phase === 'exploring' && items.length > 0 ? (
        // The same entries as the list, for the eye; keyboards and screen readers use the list.
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col gap-2 p-4 pb-[max(16px,env(safe-area-inset-bottom))]"
        >
          <Chip tone="glass" className="self-start">
            {C.nearbyLabel}
          </Chip>
          <div className="pointer-events-auto flex flex-col gap-2">
            {items.slice(0, OVERLAY_MAX).map((shown) => (
              <Label key={shown.feature.id} shown={shown} mode={mode} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );

  return (
    <StageLayout
      panel={panel}
      stage={stage}
      stageLabel={C.stageLabel}
      stageFirstOnPhone
      stageClassName="h-[56dvh]"
      className="pb-4 tablet:pb-0"
    />
  );
}
