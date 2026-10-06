'use client';

import type { Profile, ProfilePatch } from '@/account/profile';
import { AGE_CHOICES, GOAL_CHOICES, KNOWLEDGE_CHOICES } from '@/components/account/profile-options';
import { ChoiceChecks, ChoiceGroup } from '@/components/ui/choice-group';
import { messages } from '@/messages';
import { MeSection } from './me-section';
import { SaveStatus, useSaveState } from './save-status';

const P = messages.profile;

/**
 * About you: the three optional answers of master prompt v2 §5, each changed and
 * saved on its own. «Prefer not to answer» and no goal at all are answers like
 * any other, stored as `unknown` and `[]`. Never a birth date; nothing is
 * inferred. The visible statement says what the answers are used for.
 */
export function AboutSection({
  profile,
  save,
}: Readonly<{
  profile: Profile;
  save: (patch: ProfilePatch) => Promise<string | null>;
}>) {
  const { state, run } = useSaveState();
  const change = (patch: ProfilePatch) => run(() => save(patch));
  return (
    <MeSection id="about" title={P.title} description={P.statement}>
      <p className="-mt-2 m-0 text-fg-muted text-sm">{P.optional}</p>
      <ChoiceChecks
        legend={P.goals.label}
        hint={P.goals.hint}
        options={GOAL_CHOICES}
        values={profile.goals}
        onChange={(goals) => change({ goals })}
      />
      <ChoiceGroup
        legend={P.knowledge.label}
        options={KNOWLEDGE_CHOICES}
        value={profile.knowledge_level}
        onChange={(knowledge_level) => change({ knowledge_level })}
      />
      <ChoiceGroup
        legend={P.age.label}
        hint={P.age.hint}
        options={AGE_CHOICES}
        value={profile.age_range}
        onChange={(age_range) => change({ age_range })}
      />
      <SaveStatus state={state} />
    </MeSection>
  );
}
