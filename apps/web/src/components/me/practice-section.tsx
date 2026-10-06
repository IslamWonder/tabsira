import { ShieldIcon } from '@/components/icons';
import { LinkButton } from '@/components/ui/button';
import { messages } from '@/messages';
import { MeSection } from './me-section';

/**
 * The way into the practice screen (ranks, streak, the daily quest, the sky of meanings
 * and badges), with the practice-not-piety statement that must stand wherever
 * progress is shown (owner decision 27).
 */
export function PracticeSection() {
  return (
    <MeSection id="practice" title={messages.pages.me.sections.practice}>
      <div className="flex flex-col items-start gap-3">
        <p className="m-0 text-fg-soft leading-[1.85]">{messages.practiceView.teaser.body}</p>
        <LinkButton href="/sky" variant="secondary">
          {messages.practiceView.teaser.open}
        </LinkButton>
        <p className="m-0 flex items-start gap-2 text-fg-muted text-sm leading-[1.8]">
          <ShieldIcon width="18" height="18" className="mt-1 shrink-0 text-[var(--ornament)]" />
          {messages.practice.disclaimer}
        </p>
      </div>
    </MeSection>
  );
}
