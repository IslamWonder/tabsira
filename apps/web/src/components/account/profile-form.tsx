'use client';

import { type FormEvent, useId, useState } from 'react';
import type {
  AgeRange,
  Gender,
  Goal,
  KnowledgeLevel,
  ProfilePatch,
  ReligiousBackground,
} from '@/account/profile';
import { Button } from '@/components/ui/button';
import { type Choice, ChoiceChecks, ChoiceGroup } from '@/components/ui/choice-group';
import { Notice } from '@/components/ui/notice';
import { messages } from '@/messages';
import {
  AGE_CHOICES,
  GENDER_CHOICES,
  GOAL_CHOICES,
  KNOWLEDGE_CHOICES,
  RELIGION_CHOICES,
} from './profile-options';

const P = messages.profile;
const G = P.gate;

/** The goals' own «prefer not to answer»: an explicit answer, kept as an empty list. */
const NONE = 'none';
type GoalAnswer = Goal | typeof NONE;
const GOAL_ANSWERS: readonly Choice<GoalAnswer>[] = [
  ...GOAL_CHOICES,
  { value: NONE, label: G.preferNot },
];

export interface ProfileFormProps {
  /** Saves the five answers with `complete_profile`; resolves to the failure's sentence, or null once kept. */
  onSubmit: (patch: ProfilePatch) => Promise<string | null>;
}

/**
 * The whole profile, asked once, right after the account is created (decision 64): goals (any
 * number), knowledge level, age range, religious background and gender. Nothing is preselected;
 * «prefer not to answer» is a choice of its own in every question and is stored as `unknown`
 * (goals: an empty list), so the button waits only for an explicit answer to each. There is no
 * birth date and nothing is inferred. The sentence of v2 §5 stays in view above the questions.
 */
export function ProfileForm({ onSubmit }: ProfileFormProps) {
  const statementId = useId();
  const helpId = useId();
  const [goals, setGoals] = useState<GoalAnswer[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeLevel | null>(null);
  const [age, setAge] = useState<AgeRange | null>(null);
  const [religion, setReligion] = useState<ReligiousBackground | null>(null);
  const [gender, setGender] = useState<Gender | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const complete =
    goals.length > 0 && knowledge !== null && age !== null && religion !== null && gender !== null;

  // «Prefer not to answer» excludes the goals, and a goal takes it back.
  const changeGoals = (next: GoalAnswer[]) => {
    const choseNone = next.includes(NONE) && !goals.includes(NONE);
    setGoals(choseNone ? [NONE] : next.filter((goal) => goal !== NONE));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!complete || busy) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const problem = await onSubmit({
      goals: goals.filter((goal): goal is Goal => goal !== NONE),
      knowledge_level: knowledge,
      age_range: age,
      religious_background: religion,
      gender,
      complete_profile: true,
    });
    setBusy(false);
    setFailure(problem);
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-6" aria-busy={busy}>
      <p id={statementId} className="m-0 text-fg-soft leading-[1.85]">
        {G.statement} {P.optional}
      </p>
      <p id={helpId} className="m-0 font-medium text-fg-muted text-sm leading-[1.8]">
        {G.explicit}
      </p>
      <ChoiceChecks
        legend={P.goals.label}
        hint={P.goals.hint}
        options={GOAL_ANSWERS}
        values={goals}
        onChange={changeGoals}
        disabled={busy}
      />
      <ChoiceGroup
        legend={P.knowledge.label}
        options={KNOWLEDGE_CHOICES}
        value={knowledge}
        onChange={setKnowledge}
        disabled={busy}
      />
      <ChoiceGroup
        legend={P.age.label}
        hint={P.age.hint}
        options={AGE_CHOICES}
        value={age}
        onChange={setAge}
        disabled={busy}
      />
      <ChoiceGroup
        legend={P.religion.label}
        hint={P.religion.hint}
        options={RELIGION_CHOICES}
        value={religion}
        onChange={setReligion}
        disabled={busy}
      />
      <ChoiceGroup
        legend={P.gender.label}
        hint={P.gender.hint}
        options={GENDER_CHOICES}
        value={gender}
        onChange={setGender}
        disabled={busy}
      />
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
      <div className="flex flex-col gap-2">
        <Button
          type="submit"
          size="lg"
          disabled={!complete || busy}
          aria-describedby={complete ? undefined : helpId}
          className="w-full"
        >
          {busy ? G.submitting : G.submit}
        </Button>
        {complete ? null : (
          <p role="status" className="m-0 text-center text-fg-muted text-sm">
            {G.missing}
          </p>
        )}
      </div>
    </form>
  );
}
