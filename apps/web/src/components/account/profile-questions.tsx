'use client';

import { useId, useState } from 'react';
import type { AgeRange, Goal, KnowledgeLevel, ProfilePatch } from '@/account/profile';
import { Button } from '@/components/ui/button';
import { ChoiceChecks, ChoiceGroup } from '@/components/ui/choice-group';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { messages } from '@/messages';
import { AGE_CHOICES, GOAL_CHOICES, KNOWLEDGE_CHOICES } from './profile-options';

const P = messages.profile;
const QUESTIONS = ['goals', 'knowledge', 'age'] as const;
type Question = (typeof QUESTIONS)[number];

export interface ProfileQuestionsProps {
  /** How many of the three to ask (PROFILE_QUESTIONS_MAX, 0 to 3; master prompt v2 §5). */
  max?: number;
  /**
   * Keeps one answer: the account's profile, or the guest's device, as the
   * caller decides. Resolves to whether it was kept.
   */
  onAnswer: (patch: ProfilePatch) => Promise<boolean>;
  /** All asked, or all skipped. */
  onFinish: () => void;
}

/**
 * The optional questions, after the first insight only, one at a time, at
 * most three (master prompt v2 §5, tajriba S10): the goal, the prior
 * knowledge, the age range. Each can be skipped, and a skipped answer stays
 * `unknown`; there is never a birth date. The progress shown is real: it
 * counts the questions of this short task (Goal-gradient), and skipping is
 * never a loss (Parkinson's law). Ready here; wired after the done button later.
 */
export function ProfileQuestions({ max = 3, onAnswer, onFinish }: ProfileQuestionsProps) {
  const titleId = useId();
  const asked = QUESTIONS.slice(0, Math.max(0, Math.min(3, max)));
  const [step, setStep] = useState(0);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeLevel>('unknown');
  const [age, setAge] = useState<AgeRange>('unknown');
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const question: Question | undefined = asked[step];

  if (asked.length === 0) {
    return null;
  }
  if (question === undefined) {
    return (
      <GlassPanel as="section" aria-labelledby={titleId} className="flex flex-col gap-3">
        <h2 id={titleId} className="m-0 text-fg text-subheading">
          {P.flow.title}
        </h2>
        <div role="status">
          <Notice tone="success">{P.flow.done}</Notice>
        </div>
      </GlassPanel>
    );
  }

  const next = () => {
    setFailed(false);
    if (step + 1 >= asked.length) {
      setStep(asked.length);
      onFinish();
    } else {
      setStep(step + 1);
    }
  };

  const answer: ProfilePatch =
    question === 'goals'
      ? { goals }
      : question === 'knowledge'
        ? { knowledge_level: knowledge }
        : { age_range: age };
  const unanswered =
    (question === 'goals' && goals.length === 0) ||
    (question === 'knowledge' && knowledge === 'unknown') ||
    (question === 'age' && age === 'unknown');

  const save = async () => {
    if (unanswered) {
      next();
      return;
    }
    setSaving(true);
    const kept = await onAnswer(answer);
    setSaving(false);
    if (kept) {
      next();
    } else {
      setFailed(true);
    }
  };

  return (
    <GlassPanel as="section" ornate aria-labelledby={titleId} className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h2 id={titleId} className="m-0 text-fg text-subheading">
          {P.flow.title}
        </h2>
        <p className="m-0 text-fg-muted text-sm">{P.statement}</p>
      </header>
      <p className="m-0 font-semibold text-step-title text-sm">
        {P.flow.progress(step + 1, asked.length)}
      </p>
      {question === 'goals' ? (
        <ChoiceChecks
          legend={P.goals.label}
          hint={P.goals.hint}
          options={GOAL_CHOICES}
          values={goals}
          onChange={setGoals}
          disabled={saving}
        />
      ) : null}
      {question === 'knowledge' ? (
        <ChoiceGroup
          legend={P.knowledge.label}
          options={KNOWLEDGE_CHOICES}
          value={knowledge}
          onChange={setKnowledge}
          disabled={saving}
        />
      ) : null}
      {question === 'age' ? (
        <ChoiceGroup
          legend={P.age.label}
          hint={P.age.hint}
          options={AGE_CHOICES}
          value={age}
          onChange={setAge}
          disabled={saving}
        />
      ) : null}
      {failed ? (
        <div role="alert">
          <Notice tone="error">{messages.errors.server}</Notice>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2.5">
        <Button onClick={save} disabled={saving}>
          {saving ? P.saving : P.flow.saveAndContinue}
        </Button>
        <Button variant="ghost" onClick={next} disabled={saving}>
          {P.skip}
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setStep(asked.length);
            onFinish();
          }}
          disabled={saving}
          className="ms-auto"
        >
          {P.flow.skipAll}
        </Button>
      </div>
    </GlassPanel>
  );
}
