import { Chip } from '@/components/ui/chip';
import { messages } from '@/messages';

/**
 * What kind of result this is, as the API labels it: a prepared, reviewed
 * example (a calm chip), or a declared simulation of the development engine
 * (a bordered notice that cannot be missed). Nothing prepared or simulated is
 * ever presented as live analysis (AGENTS.md; tajriba LUX-15, LUX-25).
 */
export function EngineLabel({ engine, label }: Readonly<{ engine: string; label: string | null }>) {
  if (label === null) {
    return null;
  }
  if (engine !== 'demo') {
    return <Chip tone="primary">{label}</Chip>;
  }
  return (
    <div
      role="note"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius-card)] border-2 border-[var(--glow-gold)] bg-surface px-4 py-3 text-[0.9375rem] text-fg leading-[1.8]"
    >
      <Chip tone="primary">{messages.insightPage.simulation}</Chip>
      <span className="min-w-0 flex-1 font-semibold">{label}</span>
    </div>
  );
}
