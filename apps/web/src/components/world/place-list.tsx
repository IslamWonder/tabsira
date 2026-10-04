import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { type RegionView, regionState } from './world-model';

const M = messages.world.list;

/**
 * Every region and its state in words: the map's accessible twin, made a
 * visible side panel (DESIGN_DECISION.md «World»). Choosing here highlights the
 * map and choosing there highlights this list, since both share one selection.
 */
export function PlaceList({
  views,
  selected,
  onSelect,
}: {
  views: readonly RegionView[];
  selected: string | null;
  onSelect: (view: RegionView) => void;
}) {
  return (
    <section aria-labelledby="world-regions" className="flex flex-col gap-2">
      <h2 id="world-regions" className="m-0 font-semibold text-base text-fg-soft">
        {M.title}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
        {views.map((view) => {
          const opened = view.place !== null;
          return (
            <li key={view.region.id}>
              <button
                type="button"
                aria-pressed={view.region.id === selected}
                onClick={() => onSelect(view)}
                className={cx(
                  'flex min-h-12 w-full flex-col items-start justify-center gap-0.5 rounded-[var(--radius-card)] border px-4 py-2 text-start',
                  view.region.id === selected
                    ? 'border-[var(--primary)] bg-[var(--chip-primary-bg)]'
                    : 'border-line bg-surface',
                  opened ? 'text-fg' : 'text-fg-muted'
                )}
              >
                <span className="font-semibold">{view.region.name}</span>
                <span className="text-sm text-fg-muted">{regionState(view)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
