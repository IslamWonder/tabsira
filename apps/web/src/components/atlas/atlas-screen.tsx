'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useSession } from '@/account/session';
import { entriesIn, myEntries, searchPlaces } from '@/atlas/api';
import {
  type AtlasFeature,
  type AtlasFilters,
  DEFAULT_VIEW,
  EMPTY_FILTERS,
  lngLatOf,
  type MapEntryOwner,
  type Period,
  type PlaceHit,
  type Window,
} from '@/atlas/types';
import { type AtlasView, encodeViewHash, parseViewHash } from '@/atlas/view-state';
import { MapLayout } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { TextField } from '@/components/ui/text-field';
import { failureMessage } from '@/lib/api/failure-message';
import { cx } from '@/lib/cx';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import { profilePath } from '@/social/identity';
import { MapView } from './map-view';

const A = messages.atlas;
const PERIODS: readonly Period[] = ['all', 'week', 'month', 'year'];
/** Whose entries the list shows: everyone's inside the window, or the signed-in owner's own. */
type Scope = 'public' | 'mine';
const SCOPES: readonly Scope[] = ['public', 'mine'];

type View = AtlasView;

type Load =
  | { kind: 'idle' | 'loading' }
  | { kind: 'ready'; truncated: boolean }
  | { kind: 'failed'; message: string };

export function entryPath(id: string): Route {
  return `/atlas/entries/${id}` as Route;
}

export function placePath(geonameId: number): Route {
  return `/atlas/places/${geonameId}` as Route;
}

/** The card of one entry: title, glimpse, place, who published it, and the way to the insight. */
export function EntryCard({ feature, onClose }: { feature: AtlasFeature; onClose?: () => void }) {
  const { properties } = feature;
  return (
    <GlassPanel as="article" ornate className="flex flex-col gap-3" aria-label={properties.title}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="m-0 font-bold font-display text-[1.5rem] text-gilded leading-[1.3]">
          {properties.title}
        </h2>
        {onClose === undefined ? null : (
          <Button variant="ghost" onClick={onClose} className="min-h-10 px-3 text-[0.875rem]">
            {A.card.close}
          </Button>
        )}
      </div>
      <p className="m-0 text-fg-soft leading-[1.85]">{properties.glimpse}</p>
      <dl className="m-0 flex flex-col gap-1 text-[0.875rem] text-fg-muted">
        {properties.place === null ? null : (
          <div className="flex gap-2">
            <dt>{A.card.place}</dt>
            <dd className="m-0">
              <Link
                href={placePath(properties.place.geoname_id)}
                className="text-link underline-offset-4 hover:underline"
              >
                {A.joinLabels([properties.place.label, properties.place.country_label])}
              </Link>
            </dd>
          </div>
        )}
        <div className="flex gap-2">
          <dd className="m-0">{properties.precision_label}</dd>
        </div>
        <div className="flex gap-2">
          <dd className="m-0">
            {A.card.by('')}
            <Link
              href={profilePath(properties.author.handle)}
              className="text-link underline-offset-4 hover:underline"
            >
              {properties.author.public_name}
            </Link>
          </dd>
        </div>
        <div className="flex gap-2">
          <dd className="m-0">
            <time dateTime={properties.published_on}>
              {A.card.publishedAt(formatDay(properties.published_on))}
            </time>
          </dd>
        </div>
      </dl>
      <LinkButton href={entryPath(feature.id)} className="self-start">
        {A.card.open}
      </LinkButton>
    </GlassPanel>
  );
}

/** Finds a city or place by name; the atlas and the camera screen both pick a region with it. */
export function PlaceSearch({ onPick }: { onPick: (hit: PlaceHit) => void }) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<PlaceHit[] | null>(null);
  const [state, setState] = useState<'idle' | 'searching' | 'failed'>('idle');
  const listId = useId();
  const latest = useRef(0);

  const search = async () => {
    const q = query.trim();
    if (q.length < 2) {
      return;
    }
    const mine = ++latest.current;
    setState('searching');
    const result = await searchPlaces(q);
    if (mine !== latest.current) {
      return;
    }
    setState(result.ok ? 'idle' : 'failed');
    setHits(result.ok ? result.data : null);
  };

  return (
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
          label={A.search}
          placeholder={A.searchPlaceholder}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
          className="min-w-0 flex-1"
        />
        <Button type="submit" variant="secondary" disabled={state === 'searching'}>
          {state === 'searching' ? A.searching : A.search}
        </Button>
      </div>
      {state === 'failed' ? (
        <div role="alert">
          <Notice tone="error">{messages.errors.server}</Notice>
        </div>
      ) : null}
      {hits === null ? null : hits.length === 0 ? (
        <p role="status" className="m-0 text-fg-muted text-sm">
          {A.noPlaces}
        </p>
      ) : (
        <ul id={listId} className="m-0 flex list-none flex-col gap-1 p-0">
          {hits.map((hit) => (
            <li key={hit.geoname_id}>
              <button
                type="button"
                onClick={() => {
                  onPick(hit);
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
  );
}

function Filters({
  filters,
  countries,
  onChange,
  scope,
  onScope,
}: {
  filters: AtlasFilters;
  countries: readonly { iso2: string; label: string }[];
  onChange: (filters: AtlasFilters) => void;
  /** Null for a guest, who has no entries of their own. */
  scope: Scope | null;
  onScope: (scope: Scope) => void;
}) {
  const countryId = useId();
  return (
    <div className="flex flex-col gap-4">
      {scope === null ? null : (
        <ChoiceGroup
          legend={A.filters.scope}
          options={SCOPES.map((value) => ({ value, label: A.filters.scopes[value] }))}
          value={scope}
          onChange={onScope}
        />
      )}
      {filters.concept === null ? null : (
        <div className="flex flex-wrap items-center gap-2">
          <p className="m-0 text-[0.9375rem] text-fg-soft">{A.filters.conceptActive}</p>
          <Button
            variant="ghost"
            onClick={() => onChange({ ...filters, concept: null })}
            className="min-h-10 px-3 text-[0.875rem]"
          >
            {A.filters.clearConcept}
          </Button>
        </div>
      )}
      <ChoiceGroup
        legend={A.filters.period}
        options={PERIODS.map((value) => ({ value, label: A.filters.periods[value] }))}
        value={filters.period}
        onChange={(period) => onChange({ ...filters, period })}
      />
      {countries.length === 0 ? null : (
        <div className="flex flex-col gap-1.5">
          <label htmlFor={countryId} className="font-medium text-[0.9375rem] text-fg">
            {A.filters.country}
          </label>
          <select
            id={countryId}
            value={filters.country ?? ''}
            onChange={(event) =>
              onChange({
                ...filters,
                country: event.target.value === '' ? null : event.target.value,
              })
            }
            className="min-h-12 rounded-[14px] border border-line bg-surface px-3 text-fg"
          >
            <option value="">{A.filters.anyCountry}</option>
            {countries.map((country) => (
              <option key={country.iso2} value={country.iso2}>
                {country.label}
              </option>
            ))}
          </select>
        </div>
      )}
      {filters.period !== 'all' || filters.country !== null || filters.concept !== null ? (
        <Button variant="ghost" onClick={() => onChange(EMPTY_FILTERS)} className="self-start">
          {A.filters.clear}
        </Button>
      ) : null}
    </div>
  );
}

type MineLoad =
  | { kind: 'loading' }
  | { kind: 'ready'; entries: MapEntryOwner[] }
  | { kind: 'failed'; message: string };

/**
 * The owner's own entries in every state (the published-insights list, extension §4):
 * what is public opens on the atlas; the rest leads back to the placing screen.
 * The private capture point is never shown here; the public point only moves the map.
 */
function MyEntries({ onShow }: { onShow: (point: [number, number]) => void }) {
  const [load, setLoad] = useState<MineLoad>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` counts the retries; each one asks again.
  useEffect(() => {
    let current = true;
    setLoad({ kind: 'loading' });
    void myEntries().then((result) => {
      if (!current) {
        return;
      }
      setLoad(
        result.ok
          ? { kind: 'ready', entries: result.data }
          : { kind: 'failed', message: failureMessage(result) }
      );
    });
    return () => {
      current = false;
    };
  }, [attempt]);

  return (
    <section aria-label={A.mine.list} className="flex flex-col gap-3">
      <h2 className="m-0 flex items-baseline justify-between font-semibold text-[1.125rem] text-fg">
        <span>{A.mine.list}</span>
        {load.kind === 'ready' ? (
          <span className="text-[0.875rem] text-fg-muted">{A.count(load.entries.length)}</span>
        ) : null}
      </h2>
      {load.kind === 'loading' ? (
        <p role="status" className="m-0 text-fg-muted">
          {A.mine.loading}
        </p>
      ) : null}
      {load.kind === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{load.message}</Notice>
          <Button variant="ghost" onClick={() => setAttempt((n) => n + 1)}>
            {A.retry}
          </Button>
        </div>
      ) : null}
      {load.kind === 'ready' && load.entries.length === 0 ? (
        <p role="status" className="m-0 text-fg-soft leading-[1.85]">
          {A.mine.empty} {A.mine.emptyHint}
        </p>
      ) : null}
      {load.kind === 'ready' ? (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {load.entries.map((entry) => {
            const point = entry.public === null ? null : lngLatOf(entry.public.point);
            return (
              <li
                key={entry.id}
                className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line px-3 py-2.5"
              >
                <div className="flex flex-col">
                  <span className="font-semibold text-fg">{entry.title}</span>
                  <span className="text-[0.8125rem] text-fg-muted">
                    {A.joinLabels([A.publish.status[entry.status], entry.place?.label])}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {entry.status === 'published' ? (
                    <LinkButton
                      href={entryPath(entry.id)}
                      variant="secondary"
                      className="min-h-10 px-3 text-[0.875rem]"
                    >
                      {A.publish.open}
                    </LinkButton>
                  ) : null}
                  <LinkButton
                    href={`/atlas/publish?insight=${entry.insight_id}` as Route}
                    variant="ghost"
                    className="min-h-10 px-3 text-[0.875rem]"
                  >
                    {A.mine.review}
                  </LinkButton>
                  {point === null ? null : (
                    <Button
                      variant="ghost"
                      onClick={() => onShow(point)}
                      className="min-h-10 px-3 text-[0.875rem]"
                    >
                      {A.place.showOnMap}
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

/** The view the address's fragment names, read in the browser alone; the server renders none. */
function viewFromAddress(): View | null {
  return typeof window === 'undefined' ? null : parseViewHash(window.location.hash).view;
}

/**
 * The world atlas: the map with its results beside it (the accessible
 * alternative made a feature: DESIGN_DECISION.md). The page asks the API for the
 * window it shows, on display and on the search-here button, never on every
 * move; the near-me button moves the map with the device's own position and sends
 * nothing. An empty window says so and invents no point. What the page looks at
 * (centre, zoom, selection, filters) lives in the address's fragment, so the
 * camera's show-on-map link opens the same view and coming back restores it;
 * a fragment never reaches a server.
 */
export function AtlasScreen({
  initialView = null,
  cameraDiscovery = false,
}: {
  initialView?: View | null;
  /** FEATURE_CAMERA_DISCOVERY, read by the server: shows the way to the camera discovery. */
  cameraDiscovery?: boolean;
}) {
  const session = useSession();
  const [features, setFeatures] = useState<AtlasFeature[]>([]);
  const [load, setLoad] = useState<Load>({ kind: 'idle' });
  const [filters, setFilters] = useState<AtlasFilters>(EMPTY_FILTERS);
  const [scope, setScope] = useState<Scope>('public');
  const [view, setView] = useState<View | null>(() => initialView ?? viewFromAddress());
  const [selected, setSelected] = useState<string | null>(null);
  const [moved, setMoved] = useState(false);
  const [nearNote, setNearNote] = useState<string | null>(null);
  const window_ = useRef<Window | null>(null);
  // What the map shows after its last move; what the address carries.
  const [shownView, setShownView] = useState<View | null>(view);
  const latest = useRef(0);

  // The selection and filters of the address, once in the browser; the map's view was read above.
  useEffect(() => {
    const state = parseViewHash(window.location.hash);
    if (state.selected !== null) {
      setSelected(state.selected);
    }
    if (
      state.filters.period !== 'all' ||
      state.filters.country !== null ||
      state.filters.concept !== null
    ) {
      setFilters(state.filters);
    }
  }, []);

  // The address follows the page, replacing itself: coming back restores the same view.
  useEffect(() => {
    const hash = encodeViewHash({ view: shownView, selected, filters });
    window.history.replaceState(null, '', hash === '' ? window.location.pathname : hash);
  }, [selected, filters, shownView]);

  const fetchWindow = useCallback(async (window: Window, applied: AtlasFilters) => {
    const mine = ++latest.current;
    setLoad({ kind: 'loading' });
    const result = await entriesIn(window, applied);
    if (mine !== latest.current) {
      return;
    }
    if (result.ok) {
      setFeatures(result.data.features);
      setLoad({ kind: 'ready', truncated: result.data.truncated });
      setMoved(false);
    } else {
      setLoad({ kind: 'failed', message: failureMessage(result) });
    }
  }, []);

  const onMoved = useCallback(
    (window: Window, _byHand: boolean, current: View) => {
      const first = window_.current === null;
      window_.current = window;
      setShownView(current);
      if (first) {
        void fetchWindow(window, filters);
      } else {
        setMoved(true);
      }
    },
    [fetchWindow, filters]
  );

  const searchHere = () => {
    if (window_.current !== null) {
      void fetchWindow(window_.current, filters);
    }
  };

  // A filter change asks again for the same window.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (window_.current !== null) {
      void fetchWindow(window_.current, filters);
    }
  }, [filters, fetchWindow]);

  const nearMe = () => {
    setNearNote(null);
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setNearNote(A.nearMeUnavailable);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setView({ center: [position.coords.longitude, position.coords.latitude], zoom: 11 });
        setMoved(true);
      },
      () => setNearNote(A.nearMeDenied),
      { maximumAge: 60_000, timeout: 10_000 }
    );
  };

  const countries = Array.from(
    new Map(
      features
        .map((feature) => feature.properties.place)
        .filter(
          (place): place is NonNullable<typeof place> =>
            place !== null && place.country_iso2 !== null
        )
        .map((place) => [
          place.country_iso2 as string,
          place.country_label ?? (place.country_iso2 as string),
        ])
    ),
    ([iso2, label]) => ({ iso2, label })
  );
  const selectedFeature = features.find((feature) => feature.id === selected) ?? null;

  const panel = (
    <div className="flex flex-col gap-5 px-4 py-6 tablet:px-5">
      <header className="flex flex-col gap-1.5">
        <h1 className="m-0 font-bold font-display text-[2rem] text-gilded">{A.title}</h1>
        <p className="m-0 text-fg-soft leading-[1.85]">{A.lead}</p>
      </header>
      <PlaceSearch
        onPick={(hit) => {
          setView({ center: [hit.longitude, hit.latitude], zoom: 11 });
          setMoved(true);
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={nearMe}>
          {A.nearMe}
        </Button>
        {cameraDiscovery ? (
          <LinkButton href="/atlas/camera" variant="secondary">
            {A.camera.open}
          </LinkButton>
        ) : null}
        <Button
          onClick={searchHere}
          disabled={load.kind === 'loading'}
          className={cx(!moved && 'hidden')}
        >
          {A.searchHere}
        </Button>
      </div>
      <p className="m-0 text-[0.8125rem] text-fg-muted">{A.nearMeHint}</p>
      {nearNote === null ? null : (
        <p role="status" className="m-0 text-fg-soft text-sm">
          {nearNote}
        </p>
      )}
      <Filters
        filters={filters}
        countries={countries}
        onChange={setFilters}
        scope={session.status === 'signed-in' ? scope : null}
        onScope={setScope}
      />
      {selectedFeature === null ? null : (
        <div className="hidden tablet:block">
          <EntryCard feature={selectedFeature} onClose={() => setSelected(null)} />
        </div>
      )}
      {session.status === 'signed-in' && scope === 'mine' ? (
        <MyEntries
          onShow={(point) => {
            setView({ center: point, zoom: 12 });
            setMoved(true);
          }}
        />
      ) : null}
      <section
        aria-label={A.list}
        className={cx(
          'flex flex-col gap-3',
          session.status === 'signed-in' && scope === 'mine' && 'hidden'
        )}
      >
        <h2 className="m-0 flex items-baseline justify-between font-semibold text-[1.125rem] text-fg">
          <span>{A.inView}</span>
          <span className="text-[0.875rem] text-fg-muted">{A.count(features.length)}</span>
        </h2>
        {load.kind === 'loading' ? (
          <p role="status" className="m-0 text-fg-muted">
            {A.loading}
          </p>
        ) : null}
        {load.kind === 'failed' ? (
          <div role="alert" className="flex flex-col items-start gap-3">
            <Notice tone="error">{load.message}</Notice>
            <Button variant="ghost" onClick={searchHere}>
              {A.retry}
            </Button>
          </div>
        ) : null}
        {load.kind === 'ready' && features.length === 0 ? (
          <p role="status" className="m-0 text-fg-soft leading-[1.85]">
            {A.empty} {A.emptyHint}
          </p>
        ) : null}
        {load.kind === 'ready' && load.truncated ? (
          <p className="m-0 text-fg-muted text-sm">{A.truncated}</p>
        ) : null}
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {features.map((feature) => (
            <li key={feature.id}>
              <button
                type="button"
                aria-pressed={feature.id === selected}
                onClick={() => {
                  setSelected(feature.id);
                  setView({ center: lngLatOf(feature.geometry), zoom: 12 });
                }}
                className={cx(
                  'flex min-h-12 w-full flex-col items-start rounded-[var(--radius-card)] px-3 py-2 text-start transition-colors duration-200',
                  feature.id === selected ? 'bg-[var(--chip-primary-bg)]' : 'hover:bg-surface'
                )}
              >
                <span className="font-semibold text-fg">{feature.properties.title}</span>
                <span className="text-[0.8125rem] text-fg-muted">
                  {feature.properties.place?.label ?? feature.properties.precision_label}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );

  return (
    <>
      <MapLayout
        mapLabel={A.mapLabel}
        panel={panel}
        map={
          <MapView
            features={features}
            selectedId={selected}
            onSelect={setSelected}
            onMoved={onMoved}
            view={view ?? DEFAULT_VIEW}
          />
        }
        className="pb-4 tablet:pb-0"
      />
      {/* On a phone the selected entry rises as a sheet; from tablet up it sits in the panel. */}
      <div className="tablet:hidden">
        <Sheet
          open={selectedFeature !== null}
          onClose={() => setSelected(null)}
          title={selectedFeature?.properties.title ?? ''}
        >
          {selectedFeature === null ? null : <EntryCard feature={selectedFeature} />}
        </Sheet>
      </div>
    </>
  );
}
