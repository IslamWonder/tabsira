'use client';

import { useRouter } from 'next/navigation';
import {
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { LogoMark } from '@/components/brand/logo';
import { useCapture } from '@/components/capture/capture-provider';
import { BackIcon, CompassIcon, OnwardIcon, OpenBookIcon, SparkIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import type { Place, Reveal, World } from '@/world/api';
import { LandmarkIcon } from './landmark-icons';
import { useWorld } from './use-world';
import type { Point } from './world-geometry';
import {
  announcement,
  type Landmark,
  type Learned,
  landmarkOf,
  landmarks as landmarksOf,
  learned as learnedOf,
  pendingReveals,
  THEME_COLORS,
} from './world-model';
import { WorldPanel } from './world-panel';
import { HelpContent, MineContent, PlaceContent } from './world-panels';
import { type Focus, WorldStage } from './world-stage';

const M = messages.world;
const MIDDLE: Point = { x: 0.5, y: 0.5 };
// The side panel's width from tablet up (world-panel.tsx), and that breakpoint.
const PANEL_WIDTH = 460;
const TABLET_UP = '(min-width: 48rem)';
// Enough zoom for the picture to move a spot out from under a panel.
const ASIDE_ZOOM = 1.5;

/** What the world is doing (the kit's states); `saving` happens on the insight's screen, at «تمّ». */
export type WorldPhase = 'loading' | 'unavailable' | 'ready-empty' | 'ready-progress' | 'revealing';

export type WorldPanelState =
  | { kind: 'place'; placeId: string; insightId: string | null }
  | { kind: 'mine' }
  | { kind: 'help' };

/** The whole screen under the top bar (and its 1 px rule): nothing scrolls below the world. */
function Frame({ phase, children }: { phase: WorldPhase; children: ReactNode }) {
  return (
    <div
      data-phase={phase}
      className="world-root relative h-[var(--app-height)] w-full overflow-hidden tablet:h-[calc(var(--app-height)-var(--topbar-height)-1px)]"
    >
      {children}
    </div>
  );
}

/** A round pearl control; `wide` also writes its name from tablet up (a phone shows the drawing alone, as the kit does). */
function RoundButton({
  label,
  onClick,
  children,
  wide = false,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-haspopup={wide ? 'dialog' : undefined}
      onClick={onClick}
      className={cx(
        'world-pearl inline-flex h-12 min-w-12 items-center justify-center gap-2 rounded-full font-semibold text-[0.9375rem] transition-colors duration-200 hover:bg-[#ffffff] focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-2',
        wide && 'tablet:px-4'
      )}
    >
      {children}
      {wide ? (
        <span aria-hidden="true" className="hidden tablet:inline">
          {label}
        </span>
      ) : null}
    </button>
  );
}

/**
 * The few controls the world keeps (the kit's HUD): its name with the brand at
 * the start; back, help and «بصائري» (once something was learned) at the end.
 * They stay the size of the screen, whatever the zoom.
 */
function Header({ onMine, onHelp }: { onMine: (() => void) | null; onHelp: (() => void) | null }) {
  const router = useRouter();
  const back = () => {
    if (window.history.length > 1) {
      router.back();
    } else {
      router.push('/');
    }
  };
  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-2 px-3 pt-[max(12px,env(safe-area-inset-top))] tablet:px-7 tablet:pt-6">
      <div className="world-pearl pointer-events-auto flex items-center gap-2.5 rounded-[18px] px-3 py-2 tablet:px-4">
        <LogoMark className="h-9 text-[var(--world-gold)] tablet:hidden" />
        <div className="flex flex-col">
          <h1 className="m-0 font-bold font-display text-[1.5rem] leading-[1.3]">{M.title}</h1>
          <span className="text-[0.75rem] text-[#4a635c] leading-[1.4] tablet:hidden">
            {M.brand}
          </span>
        </div>
      </div>
      <div className="pointer-events-auto flex items-center gap-1.5 tablet:gap-2">
        {onMine === null ? null : (
          <RoundButton label={M.mine} onClick={onMine} wide>
            <OpenBookIcon width="20" height="20" />
          </RoundButton>
        )}
        {onHelp === null ? null : (
          <RoundButton label={M.help} onClick={onHelp}>
            <CompassIcon width="22" height="22" />
          </RoundButton>
        )}
        <RoundButton label={M.back} onClick={back}>
          <BackIcon width="22" height="22" />
        </RoundButton>
      </div>
    </header>
  );
}

/** The invitation and the one way on: capturing a scene, wherever the reader is. */
function Discover({ empty }: { empty: boolean }) {
  const capture = useCapture();
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-[calc(var(--nav-clearance)-8px)] z-10 flex flex-col items-center gap-3 pr-3 pl-[76px] tablet:bottom-7 tablet:px-0">
      {empty ? (
        <p className="world-invitation m-0 text-center font-bold font-display text-[1.5rem] text-[var(--world-ink)]">
          {M.invitation}
        </p>
      ) : null}
      <button
        type="button"
        onClick={capture.open}
        aria-haspopup="dialog"
        className="pointer-events-auto inline-flex h-14 items-center gap-2 whitespace-nowrap rounded-[18px] bg-[var(--world-green)] px-4 font-semibold text-[#ffffff] text-base tablet:gap-3 tablet:px-6 tablet:text-[1.0625rem] shadow-[0_10px_28px_rgb(8_46_37/0.4)] transition-[filter] duration-200 hover:brightness-110 focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-3"
      >
        <SparkIcon width="20" height="20" className="text-[var(--world-gold)]" />
        <span>{empty ? M.discoverFirst : M.discoverMore}</span>
        <OnwardIcon width="18" height="18" />
      </button>
    </div>
  );
}

/**
 * Where a spot shows best while a panel stays open over the picture: left of the side
 * panel from tablet up (it opens at the start, the right), above the bottom sheet on a phone.
 */
function besidePanel(): Point {
  if (window.matchMedia(TABLET_UP).matches) {
    return { x: -PANEL_WIDTH / 2, y: 0 };
  }
  return { x: 0, y: -window.innerHeight * 0.22 };
}

function landmarkLabel(landmark: Landmark): string {
  const insights = landmark.place?.insights ?? [];
  return M.landmark(
    landmark.name,
    Math.max(insights.length, 1),
    insights.at(-1)?.title ?? landmark.name
  );
}

export interface WorldViewProps {
  world: World;
  onVisited: (place: Place) => void;
  onShown: (ids: readonly string[]) => void;
  /** A panel open from the start, for the gallery's still pictures. */
  initialPanel?: WorldPanelState | null;
}

/**
 * The personal world as one picture under clouds (decision 59, the owners'
 * world kit). A newcomer sees clouds only, an invitation and «اكتشف أول
 * بصيرة»: no ground, no names, no list, no count. Each concept learned with
 * «تمّ» has lifted the clouds from its circle, with a landmark where its
 * region's first concept was learned; a landmark opens what was learned there,
 * «بصائري» lists all of it. A reveal the world has not shown yet plays here
 * once, wherever the learning happened, and is announced; the camera goes to
 * it once, and never moves by itself otherwise.
 */
export function WorldView({ world, onVisited, onShown, initialPanel = null }: WorldViewProps) {
  const landmarks = useMemo(() => landmarksOf(world), [world]);
  const items = useMemo(() => learnedOf(world), [world]);
  const pending = useMemo(() => pendingReveals(world), [world]);
  const [panel, setPanel] = useState<WorldPanelState | null>(initialPanel);
  const [spoken, setSpoken] = useState('');
  const latest = pending.at(-1) ?? world.reveals.at(-1) ?? null;
  const home: Point = latest === null ? MIDDLE : { x: latest.x, y: latest.y };
  const [focus, setFocus] = useState<Focus>({ point: home, key: 0, fly: false });
  const worldRef = useRef(world);
  const seenPending = useRef(pending.map((reveal) => reveal.id).join());

  useLayoutEffect(() => {
    worldRef.current = world;
  }, [world]);

  // A reveal that arrives while the world is open (learned in another tab): the camera goes there, once.
  useEffect(() => {
    const ids = pending.map((reveal) => reveal.id).join();
    const newest = pending.at(-1);
    if (ids === seenPending.current || newest === undefined) {
      seenPending.current = ids;
      return;
    }
    seenPending.current = ids;
    setFocus((current) => ({
      point: { x: newest.x, y: newest.y },
      key: current.key + 1,
      fly: true,
    }));
  }, [pending]);

  const played = useCallback(
    (ids: readonly string[]) => {
      setSpoken(announcement(worldRef.current, ids));
      onShown(ids);
    },
    [onShown]
  );

  const flyTo = (point: Point, aside?: Point) =>
    setFocus((current) => ({
      point,
      key: current.key + 1,
      fly: true,
      ...(aside === undefined ? {} : { shift: aside, minZoom: ASIDE_ZOOM }),
    }));

  const goTo = (insightId: string) => {
    setPanel(null);
    // A reload may have taken the insight away since the panel opened: then it only closes.
    const item = items.find((entry) => entry.insight.id === insightId && entry.spot !== null);
    if (item === undefined) {
      return;
    }
    const spot = item.spot as Reveal;
    flyTo({ x: spot.x, y: spot.y });
    const landmark = landmarkOf(world, item.place.id);
    // After the panel has given focus back: to the landmark the camera went to.
    requestAnimationFrame(() => {
      if (landmark !== null) {
        document.querySelector<HTMLElement>(`[data-landmark="${landmark.id}"]`)?.focus();
      }
    });
  };

  const pick = (item: Learned) => {
    setPanel({ kind: 'place', placeId: item.place.id, insightId: item.insight.id });
    if (item.spot !== null) {
      flyTo({ x: item.spot.x, y: item.spot.y }, besidePanel());
    }
  };

  const place =
    panel?.kind === 'place'
      ? (world.places.find((item) => item.id === panel.placeId) ?? null)
      : null;
  const placeLandmark = place === null ? null : landmarkOf(world, place.id);
  const close = () => setPanel(null);
  const empty = items.length === 0;
  let phase: WorldPhase = empty ? 'ready-empty' : 'ready-progress';
  if (pending.length > 0) {
    phase = 'revealing';
  }

  let title: string = M.helpView.title;
  let description: string = M.helpView.lead;
  let body: ReactNode = <HelpContent onLeave={close} />;
  if (panel?.kind === 'mine') {
    title = M.mineView.title;
    description = M.mineView.lead;
    body = <MineContent items={items} onPick={pick} />;
  } else if (place !== null && panel?.kind === 'place') {
    title = place.name;
    description = M.panel.placeLead;
    body = (
      <PlaceContent
        key={place.id}
        place={place}
        insightId={panel.insightId}
        onChoose={(insightId) => setPanel({ kind: 'place', placeId: place.id, insightId })}
        onGoTo={goTo}
        onVisited={onVisited}
      />
    );
  }

  return (
    <Frame phase={phase}>
      <WorldStage
        reveals={world.reveals}
        landmarks={landmarks}
        pending={pending}
        onPlayed={played}
        focus={focus}
        home={home}
        label={landmarkLabel}
        onOpen={(landmark) =>
          setPanel({ kind: 'place', placeId: landmark.reveal.place_id, insightId: null })
        }
      />
      <Header
        onMine={empty ? null : () => setPanel({ kind: 'mine' })}
        onHelp={() => setPanel({ kind: 'help' })}
      />
      <Discover empty={empty} />
      <p role="status" className="sr-only">
        {spoken}
      </p>
      <WorldPanel
        open={panel !== null && (panel.kind !== 'place' || place !== null)}
        onClose={close}
        title={title}
        description={description}
        icon={
          placeLandmark === null || panel?.kind !== 'place' ? undefined : (
            <LandmarkIcon
              icon={placeLandmark.icon}
              style={{ color: THEME_COLORS[placeLandmark.theme] }}
            />
          )
        }
      >
        {body}
      </WorldPanel>
    </Frame>
  );
}

/** Clouds only, the way the world looks before it is read: never an empty world that is not one. */
function Waiting({ failed, onRetry }: { failed: boolean; onRetry: () => void }) {
  return (
    <Frame phase={failed ? 'unavailable' : 'loading'}>
      <div aria-hidden="true" className="world-clouds absolute inset-0" />
      <Header onMine={null} onHelp={null} />
      <div className="absolute inset-0 flex items-center justify-center px-6">
        {failed ? (
          <div className="world-pearl flex max-w-sm flex-col items-center gap-3 rounded-[20px] px-5 py-4 text-center">
            <p role="alert" className="m-0 leading-[1.8]">
              {M.unavailable}
            </p>
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex min-h-12 items-center rounded-full bg-[var(--world-green)] px-6 font-semibold text-[#ffffff] focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-2"
            >
              {M.retry}
            </button>
          </div>
        ) : (
          <p role="status" className="world-pearl m-0 rounded-full px-5 py-2.5">
            {M.loading}
          </p>
        )}
      </div>
    </Frame>
  );
}

/** The personal world, loaded for its owner: clouds while it loads, clouds and a retry when it cannot. */
export function WorldScreen() {
  const { load, reload, replacePlace, markShown } = useWorld();
  if (load.status !== 'ready') {
    return <Waiting failed={load.status === 'failed'} onRetry={reload} />;
  }
  return <WorldView world={load.world} onVisited={replacePlace} onShown={markShown} />;
}
