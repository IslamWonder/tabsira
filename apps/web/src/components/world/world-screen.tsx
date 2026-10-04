'use client';

import { useMemo, useState } from 'react';
import { Button, LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';
import { type Place, visitPlace, type World } from '@/world/api';
import { FogMap } from './fog-map';
import { PlaceDetail } from './place-detail';
import { PlaceList } from './place-list';
import { ThreadList } from './thread-list';
import { useWorld } from './use-world';
import { openedCount, type RegionView, regionViews, threads as threadsOf } from './world-model';

const M = messages.world;

function Invitation() {
  return (
    <GlassPanel
      as="section"
      ornate
      aria-labelledby="world-invitation"
      className="flex flex-col items-start gap-3"
    >
      <h2 id="world-invitation" className="m-0 font-bold font-display text-[1.5rem] text-gilded">
        {M.empty.title}
      </h2>
      <p className="m-0 text-fg-soft leading-[1.9]">{M.empty.body}</p>
      <LinkButton href="/" variant="primary" size="lg">
        {M.empty.cta}
      </LinkButton>
    </GlassPanel>
  );
}

function Notice({ text, onRetry }: { text: string | null; onRetry?: () => void }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-6 py-16 text-center">
      <h1 className="m-0 font-bold font-display text-[1.75rem] text-gilded">
        {messages.pages.world.title}
      </h1>
      <p role={onRetry ? 'alert' : 'status'} className="m-0 text-fg-soft leading-[1.9]">
        {text}
      </p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          {M.retry}
        </Button>
      ) : null}
    </div>
  );
}

type Visited = (place: Place) => void;

export function WorldView({
  world,
  onVisited,
  initialSelected = null,
}: {
  world: World;
  onVisited: Visited;
  /** Opens a region at first, for the gallery's still pictures. */
  initialSelected?: string | null;
}) {
  const [selected, setSelected] = useState<string | null>(initialSelected);
  const [activeThread, setActiveThread] = useState<string | null>(null);
  const views = useMemo(() => regionViews(world), [world]);
  const threads = useMemo(() => threadsOf(views, world.relations), [views, world.relations]);
  const selectedView = views.find((view) => view.region.id === selected);

  function select(view: RegionView) {
    setSelected(view.region.id);
    if (view.place) {
      void visit(view.place.id, onVisited);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 pt-[max(24px,env(safe-area-inset-top))] pb-4 tablet:grid tablet:grid-cols-[20rem_minmax(0,1fr)] tablet:items-start tablet:gap-x-6 tablet:px-6 tablet:py-6 desktop:grid-cols-[26rem_minmax(0,1fr)] desktop:px-10">
      <header className="flex flex-col gap-1 tablet:col-start-1 tablet:row-start-1">
        <h1 className="m-0 font-bold font-display text-[2rem] text-fg">
          {messages.pages.world.title}
        </h1>
        <p className="m-0 text-fg-muted text-sm leading-[1.8]">
          {M.summary(openedCount(views), views.length)}
        </p>
      </header>
      <section
        aria-label={messages.pages.world.mapLabel}
        className="relative aspect-[3/4] w-full overflow-hidden rounded-[var(--radius-panel)] border border-line tablet:sticky tablet:top-[calc(var(--topbar-height)+1.5rem)] tablet:col-start-2 tablet:row-span-2 tablet:row-start-1 tablet:aspect-auto tablet:h-[calc(var(--app-height)-var(--topbar-height)-3rem)]"
      >
        <FogMap
          views={views}
          threads={threads}
          selected={selected}
          activeThread={activeThread}
          onSelect={select}
        />
      </section>
      <div className="flex min-w-0 flex-col gap-5 tablet:col-start-1 tablet:row-start-2">
        {selectedView ? (
          <PlaceDetail
            key={selectedView.region.id}
            view={selectedView}
            onClose={() => setSelected(null)}
          />
        ) : null}
        {world.places.length === 0 ? <Invitation /> : null}
        <PlaceList views={views} selected={selected} onSelect={select} />
        <ThreadList
          threads={threads}
          views={views}
          active={activeThread}
          onActive={setActiveThread}
        />
      </div>
    </div>
  );
}

/** Opening a place is recorded; what it returns (a treasure now ready) replaces the place. */
async function visit(placeId: string, onVisited: Visited) {
  const result = await visitPlace(placeId);
  if (result.ok) {
    onVisited(result.data);
  }
}

/**
 * The personal world (master prompt v2 §16): a fog map of the learning path's
 * regions with a side list that says the same in text, the threads between
 * places and the places' saved insights. Nothing here is a score.
 */
export function WorldScreen() {
  const { load, reload, replacePlace } = useWorld();
  if (load.status === 'loading') {
    return <Notice text={M.loading} />;
  }
  if (load.status === 'failed') {
    return <Notice text={M.unavailable} onRetry={reload} />;
  }
  return <WorldView world={load.world} onVisited={replacePlace} />;
}
