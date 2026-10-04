import {
  AGE_RANGES,
  type AgeRange,
  GENDERS,
  type Gender,
  GOALS,
  type Goal,
  KNOWLEDGE_LEVELS,
  type KnowledgeLevel,
  RELIGIOUS_BACKGROUNDS,
  type ReligiousBackground,
} from '@/account/profile';
import type { Choice } from '@/components/ui/choice-group';
import { messages } from '@/messages';

const P = messages.profile;

/** Every answer of the profile, labelled in Arabic, in the order they are offered. */
export const GOAL_CHOICES: readonly Choice<Goal>[] = GOALS.map((value) => ({
  value,
  label: P.goals.options[value],
}));
export const KNOWLEDGE_CHOICES: readonly Choice<KnowledgeLevel>[] = KNOWLEDGE_LEVELS.map(
  (value) => ({ value, label: P.knowledge.options[value] })
);
export const AGE_CHOICES: readonly Choice<AgeRange>[] = AGE_RANGES.map((value) => ({
  value,
  label: P.age.options[value],
}));
export const RELIGION_CHOICES: readonly Choice<ReligiousBackground>[] = RELIGIOUS_BACKGROUNDS.map(
  (value) => ({ value, label: P.religion.options[value] })
);
export const GENDER_CHOICES: readonly Choice<Gender>[] = GENDERS.map((value) => ({
  value,
  label: P.gender.options[value],
}));
