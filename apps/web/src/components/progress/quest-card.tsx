import { type QuestEntry, QuestLog } from '@/components/fx/quest-log';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';
import type { Progress } from '@/progress/api';

const M = messages.practiceView.quest;

/** The first step not done yet is the current one; the rest wait, so the path stays in view. */
export function questEntries(steps: Progress['daily_quest']['steps']): QuestEntry[] {
  const current = steps.findIndex((step) => !step.done);
  return steps.map((step, index) => ({
    key: step.id,
    label: step.label,
    state: step.done ? 'done' : index === current ? 'current' : 'pending',
  }));
}

/**
 * The daily quest: the day's quest, with the API's own title and step labels.
 * Not done is stated plainly; nothing is lost and nothing is promised.
 */
export function QuestCard({ quest }: { quest: Progress['daily_quest'] }) {
  return (
    <GlassPanel as="section" aria-labelledby="practice-quest" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="practice-quest" className="m-0 font-bold font-display text-heading text-fg">
          {quest.title}
        </h2>
        <Chip tone={quest.done ? 'primary' : 'neutral'}>{quest.done ? M.done : M.pending}</Chip>
      </div>
      <QuestLog entries={questEntries(quest.steps)} />
      <p className="m-0 text-fg-muted text-sm">{M.daysDone(quest.days_done)}</p>
    </GlassPanel>
  );
}
