import { GeometricPattern } from '@/components/fx/geometric-pattern';
import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';
import { SparkIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { type RegionView, regionState, type Thread } from './world-model';

const M = messages.world;

export interface FogMapProps {
  views: readonly RegionView[];
  threads: readonly Thread[];
  /** The selected region's id. */
  selected: string | null;
  /** The thread being read in the list, drawn stronger. */
  activeThread: string | null;
  onSelect: (view: RegionView) => void;
}

/*
 * Region positions are ratios of the map measured from its left edge (the
 * fixed map in data/world/regions-1.0.json), so they are placed with physical
 * left and top whatever the reading direction: the map is a picture, not text.
 */
function at(x: number, y: number) {
  return { left: `${x * 100}%`, top: `${y * 100}%` };
}

function Cloud({ view }: { view: RegionView }) {
  const { x, y } = view.region.position;
  return (
    <span
      aria-hidden="true"
      data-fog={view.region.id}
      className="pointer-events-none absolute aspect-[1.25] w-[46%] -translate-x-1/2 -translate-y-1/2 motion-safe:animate-fade-in"
      style={{
        ...at(x, y),
        background: 'radial-gradient(closest-side, var(--stage-fade) 40%, transparent 100%)',
        opacity: 0.94,
      }}
    />
  );
}

function Glow({ view }: { view: RegionView }) {
  const { x, y } = view.region.position;
  return (
    <span
      aria-hidden="true"
      data-glow={view.region.id}
      className="pointer-events-none absolute aspect-square w-[34%] -translate-x-1/2 -translate-y-1/2 motion-safe:animate-breathe"
      style={{
        ...at(x, y),
        background: 'radial-gradient(closest-side, var(--glow-gold) 0%, transparent 100%)',
        opacity: 0.32,
      }}
    />
  );
}

function Node({ opened }: { opened: boolean }) {
  return opened ? (
    <svg width="30" height="30" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <polygon
        points={starPoints(12, 12, 11, 11 * KHATAM_RATIO)}
        style={{ fill: 'var(--glow-gold)', stroke: 'var(--ornament)' }}
        strokeWidth={0.8}
      />
    </svg>
  ) : (
    <span className="size-3 rounded-full border border-[var(--text-muted)] border-dashed" />
  );
}

function RegionButton({
  view,
  selected,
  onSelect,
}: {
  view: RegionView;
  selected: boolean;
  onSelect: (view: RegionView) => void;
}) {
  const { id, name, position } = view.region;
  const opened = view.place !== null;
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={M.map.select(name, regionState(view))}
      data-region={id}
      onClick={() => onSelect(view)}
      className="absolute flex w-28 -translate-x-1/2 -translate-y-6 flex-col items-center gap-1 rounded-[var(--radius-card)] bg-transparent p-0"
      style={at(position.x, position.y)}
    >
      <span
        aria-hidden="true"
        className={cx(
          'relative flex size-12 items-center justify-center rounded-full border',
          opened ? 'glass border-[var(--quran-border)]' : 'border-line bg-surface',
          selected &&
            'shadow-[var(--primary-glow)] outline outline-2 outline-[var(--primary)] outline-offset-2'
        )}
      >
        <Node opened={opened} />
        {view.hasTreasure ? (
          <SparkIcon
            width="16"
            height="16"
            className="absolute -top-1 -end-1 text-[var(--glow-gold)] motion-safe:animate-breathe"
          />
        ) : null}
      </span>
      <span
        aria-hidden="true"
        className={cx(
          'rounded-full px-2 py-0.5 text-center font-medium text-xs leading-snug',
          opened ? 'glass text-glass-fg' : 'hidden text-fg-muted tablet:block',
          selected && !opened && 'block glass text-glass-fg'
        )}
      >
        {name}
      </span>
    </button>
  );
}

/**
 * The fog map: one fixed map under fog, with a clearing and a glow where a
 * place was made (Zeigarnik effect: the unopened stays in view without a score).
 * A dotted thread joins two places only for a recorded relation. Every region
 * is a real button; the list beside it is the same content in text.
 */
export function FogMap({ views, threads, selected, activeThread, onSelect }: FogMapProps) {
  return (
    <div className="stage-aurora relative isolate size-full min-h-[26rem] overflow-hidden bg-surface">
      <GeometricPattern kind={6} />
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="absolute inset-0 size-full"
      >
        {threads.map((thread) => {
          const active = thread.key === activeThread;
          return (
            <line
              key={thread.key}
              data-thread={thread.key}
              x1={thread.from.region.position.x * 100}
              y1={thread.from.region.position.y * 100}
              x2={thread.to.region.position.x * 100}
              y2={thread.to.region.position.y * 100}
              vectorEffect="non-scaling-stroke"
              strokeLinecap="round"
              strokeDasharray={active ? '1 7' : '1 9'}
              strokeWidth={active ? 3 : 2}
              style={{ stroke: 'var(--glow-gold)', opacity: active ? 1 : 0.7 }}
              className="motion-safe:animate-fade-in"
            />
          );
        })}
      </svg>
      {views.map((view) =>
        view.place === null ? (
          <Cloud key={view.region.id} view={view} />
        ) : (
          <Glow key={view.region.id} view={view} />
        )
      )}
      {views.map((view) => (
        <RegionButton
          key={view.region.id}
          view={view}
          selected={view.region.id === selected}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
