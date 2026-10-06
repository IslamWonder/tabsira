'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { memo, useCallback, useEffect, useId, useRef, useState } from 'react';
import { useSession } from '@/account/session';
import { myEntries, searchPlaces } from '@/atlas/api';
import {
  type AtlasFeature,
  type AtlasFilters,
  DEFAULT_VIEW,
  EMPTY_FILTERS,
  isCluster,
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
import { memberLabel, profilePath } from '@/social/identity';
import { MapView } from './map-view';
import { MySponsorships } from './my-sponsorships';
import { OrphansSection } from './orphans-section';
import { entryPath, placePath } from './paths';
import { useAtlasData } from './use-atlas-data';

const A = messages.atlas;
const S = messages.atlas.sponsor;
const PERIODS: readonly Period[] = ['all', 'week', 'month', 'year'];
/** Whose entries the list shows: everyone's inside the window, or the signed-in owner's own. */
type Scope = 'public' | 'mine' | 'sponsored';
const SCOPES: readonly Scope[] = ['public', 'mine'];
/** The member's sponsorships join the scopes only while the sponsoring feature is on. */
const SCOPES_WITH_SPONSORING: readonly Scope[] = ['public', 'mine', 'sponsored'];

type View = AtlasView;

export { entryPath, placePath };

/** The card of one entry: title, glimpse, place, who published it, and the way to the insight. */
export function EntryCard({
  feature,
  onClose,
}: Readonly<{ feature: AtlasFeature; onClose?: () => void }>) {
  const { properties } = feature;
  return (
    <GlassPanel as="article" ornate className="flex flex-col gap-3" aria-label={properties.title}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="m-0 font-bold font-display text-heading text-gilded">{properties.title}</h2>
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
        {properties.author === null ? null : (
          <div className="flex gap-2">
            <dd className="m-0">
              {A.card.by('')}
              <Link
                href={profilePath(properties.author.handle)}
                className="text-link underline-offset-4 hover:underline"
              >
                {memberLabel(properties.author)}
              </Link>
            </dd>
          </div>
        )}
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

/** One row of the list; memoised so a move that changes nothing for it does not redraw it. */
const EntryRow = memo(function EntryRow({
  feature,
  selected,
  onPick,
}: {
  feature: AtlasFeature;
  selected: boolean;
  onPick: (feature: AtlasFeature) => void;
}) {
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onPick(feature)}
        className={cx(
          'flex min-h-12 w-full flex-col items-start rounded-[var(--radius-card)] px-3 py-2 text-start transition-colors duration-200',
          selected ? 'bg-[var(--chip-primary-bg)]' : 'hover:bg-surface'
        )}
      >
        <span className="font-semibold text-fg">{feature.properties.title}</span>
        <span className="text-[0.8125rem] text-fg-muted">
          {feature.properties.place?.label ?? feature.properties.precision_label}
        </span>
      </button>
    </li>
  );
});

/** Finds a city or place by name; the atlas and the camera screen both pick a region with it. */
export function PlaceSearch({ onPick }: Readonly<{ onPick: (hit: PlaceHit) => void }>) {
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
      {hits?.length === 0 ? (
        <p role="status" className="m-0 text-fg-muted text-sm">
          {A.noPlaces}
        </p>
      ) : null}
      {hits !== null && hits.length > 0 ? (
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
      ) : null}
    </form>
  );
}

function Filters({
  filters,
  countries,
  onChange,
  scope,
  onScope,
  sponsorship,
}: Readonly<{
  filters: AtlasFilters;
  countries: readonly { iso2: string; label: string }[];
  onChange: (filters: AtlasFilters) => void;
  /** Null for a guest, who has no entries of their own. */
  scope: Scope | null;
  onScope: (scope: Scope) => void;
  sponsorship: boolean;
}>) {
  const countryId = useId();
  return (
    <div className="flex flex-col gap-4">
      {scope === null ? null : (
        <ChoiceGroup
          legend={A.filters.scope}
          options={(sponsorship ? SCOPES_WITH_SPONSORING : SCOPES).map((value) => ({
            value,
            label: A.filters.scopes[value],
          }))}
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
            className="min-h-12 rounded-[14px] border border-field bg-surface px-3 text-fg"
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
function MyEntries({ onShow }: Readonly<{ onShow: (point: [number, number]) => void }>) {
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
      <h2 className="m-0 flex items-baseline justify-between font-semibold text-lg text-fg">
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
                  {entry.sponsor == null ? null : (
                    <span className="text-[0.8125rem] text-fg-soft">
                      {S.mine.by(
                        entry.sponsor.public_name === null
                          ? `@${entry.sponsor.handle}`
                          : `${entry.sponsor.public_name} @${entry.sponsor.handle}`
                      )}
                    </span>
                  )}
                  {entry.widened == null ? null : (
                    <span className="text-[0.8125rem] text-fg-muted leading-[1.8]">
                      {S.mine.widened(
                        entry.widened.label ?? S.mine.levels[entry.widened.level],
                        formatDay(entry.widened.at)
                      )}
                    </span>
                  )}
                  {entry.status === 'orphaned' && entry.sponsor == null && entry.widened == null ? (
                    <span className="text-[0.8125rem] text-fg-muted leading-[1.8]">
                      {S.mine.orphaned}
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {entry.status === 'published' || entry.status === 'orphaned' ? (
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
  sponsorship = false,
}: Readonly<{
  initialView?: View | null;
  /** The camera_discovery feature, read by the server: shows the way to the camera discovery. */
  cameraDiscovery?: boolean;
  /** The atlas_sponsorship feature, read by the server: shows the orphaned entries and the member's sponsorships. */
  sponsorship?: boolean;
}>) {
  const session = useSession();
  const [filters, setFilters] = useState<AtlasFilters>(EMPTY_FILTERS);
  const [scope, setScope] = useState<Scope>('public');
  const [view, setView] = useState<View | null>(() => initialView ?? viewFromAddress());
  const [selected, setSelected] = useState<string | null>(null);
  const [nearNote, setNearNote] = useState<string | null>(null);
  // What the map shows after its last move; what the address carries.
  const [shownView, setShownView] = useState<View | null>(view);
  const { map, list, listCentre, onMoved: onWindow, loadMore, retry } = useAtlasData(filters);

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

  const onMoved = useCallback(
    (window: Window, byHand: boolean, current: View) => {
      setShownView(current);
      onWindow(window, byHand, current);
    },
    [onWindow]
  );

  const flyToEntry = useCallback((feature: AtlasFeature) => {
    setSelected(feature.id);
    setView({ center: lngLatOf(feature.geometry), zoom: 12 });
  }, []);

  const nearMe = () => {
    setNearNote(null);
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setNearNote(A.nearMeUnavailable);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setView({ center: [position.coords.longitude, position.coords.latitude], zoom: 11 });
      },
      () => setNearNote(A.nearMeDenied),
      { maximumAge: 60_000, timeout: 10_000 }
    );
  };

  const entries = map.features.filter((feature): feature is AtlasFeature => !isCluster(feature));
  const known = [...list.items, ...entries];
  const countries = Array.from(
    new Map(
      known
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
  // An entry picked on the map keeps its card after a move that no longer lists it.
  const found = known.find((feature) => feature.id === selected) ?? null;
  const [pinned, setPinned] = useState<AtlasFeature | null>(null);
  useEffect(() => {
    if (found !== null) {
      setPinned(found);
    }
  }, [found]);
  const selectedFeature = found ?? (pinned?.id === selected ? pinned : null);

  const panel = (
    <div className="flex flex-col gap-5 px-4 py-6 tablet:px-5">
      <header className="flex flex-col gap-1.5">
        <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
          {A.title}
        </h1>
        <p className="m-0 text-fg-soft leading-[1.85]">{A.lead}</p>
      </header>
      <PlaceSearch
        onPick={(hit) => {
          setView({ center: [hit.longitude, hit.latitude], zoom: 11 });
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
        sponsorship={sponsorship}
      />
      {selectedFeature === null ? null : (
        <div className="hidden tablet:block">
          <EntryCard feature={selectedFeature} onClose={() => setSelected(null)} />
        </div>
      )}
      {sponsorship && session.status === 'signed-in' && scope === 'sponsored' ? (
        <MySponsorships />
      ) : null}
      {session.status === 'signed-in' && scope === 'mine' ? (
        <MyEntries
          onShow={(point) => {
            setView({ center: point, zoom: 12 });
          }}
        />
      ) : null}
      <section
        aria-label={A.list}
        className={cx(
          'flex flex-col gap-3',
          session.status === 'signed-in' && scope !== 'public' && 'hidden'
        )}
      >
        <h2 className="m-0 flex items-baseline justify-between font-semibold text-lg text-fg">
          <span>{A.inView}</span>
          <span className="text-[0.875rem] text-fg-muted">{A.count(list.total)}</span>
        </h2>
        {list.status === 'loading' && list.items.length === 0 ? (
          <p role="status" className="m-0 text-fg-muted">
            {A.loading}
          </p>
        ) : null}
        {list.status === 'failed' || map.status === 'failed' ? (
          <div role="alert" className="flex flex-col items-start gap-3">
            <Notice tone="error">{list.message ?? map.message}</Notice>
            <Button variant="ghost" onClick={retry}>
              {A.retry}
            </Button>
          </div>
        ) : null}
        {list.status === 'ready' && list.items.length === 0 ? (
          <p role="status" className="m-0 text-fg-soft leading-[1.85]">
            {A.empty} {A.emptyHint}
          </p>
        ) : null}
        {map.status === 'ready' && map.truncated ? (
          <p className="m-0 text-fg-muted text-sm">{A.truncated}</p>
        ) : null}
        <ul aria-busy={list.status === 'loading'} className="m-0 flex list-none flex-col gap-1 p-0">
          {list.items.map((feature) => (
            <EntryRow
              key={feature.id}
              feature={feature}
              selected={feature.id === selected}
              onPick={flyToEntry}
            />
          ))}
        </ul>
        {list.cursor === null ? null : (
          <>
            {list.more === 'failed' ? (
              <p role="alert" className="m-0 text-fg-muted text-sm">
                {A.loadMoreFailed}
              </p>
            ) : null}
            <Button
              variant="secondary"
              onClick={() => void loadMore()}
              disabled={list.more === 'loading' || list.status === 'loading'}
              className="self-start"
            >
              {list.more === 'loading' ? A.loadingMore : A.loadMore}
            </Button>
          </>
        )}
      </section>
      {sponsorship && (session.status !== 'signed-in' || scope === 'public') ? (
        <OrphansSection point={listCentre} />
      ) : null}
    </div>
  );

  return (
    <>
      <MapLayout
        mapLabel={A.mapLabel}
        panel={panel}
        map={
          <MapView
            features={map.features}
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
