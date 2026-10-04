import { ShieldIcon } from '@/components/icons';
import { Chip } from '@/components/ui/chip';
import { messages } from '@/messages';
import { MeSection } from './me-section';

/**
 * Where practice ranks, the streak and badges will appear (owner decision 27),
 * with the practice-not-piety statement already in place: it must stand
 * wherever progress is shown (GAMIFICATION.md §0).
 */
export function PracticeSection() {
  return (
    <MeSection id="practice" title={messages.pages.me.sections.practice}>
      <div className="flex flex-col items-start gap-3">
        <Chip tone="primary">{messages.comingSoon.badge}</Chip>
        <p className="m-0 text-fg-soft leading-[1.85]">{messages.pages.me.practice.body}</p>
        <p className="m-0 flex items-start gap-2 text-fg-muted text-sm leading-[1.8]">
          <ShieldIcon width="18" height="18" className="mt-1 shrink-0 text-[var(--ornament)]" />
          {messages.practice.disclaimer}
        </p>
      </div>
    </MeSection>
  );
}
