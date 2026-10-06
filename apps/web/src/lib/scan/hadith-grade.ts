import { messages } from '@/messages';

/** One grade as the hadith's dataset gives it (`informational_grades` of the API). */
export interface DatasetGrade {
  name: string;
  grade: string;
}

/**
 * The line naming the first grader of the dataset whose name and grade we can
 * write in Arabic, e.g. «حكم الألباني: صحيح» (decision 69), or null when there
 * is none: Bukhari, Muslim, Ahmad and al-Darimi carry no grades.
 */
export function hadithGradeLine(grades: readonly DatasetGrade[] | null | undefined): string | null {
  for (const { name, grade } of grades ?? []) {
    const grader = messages.evidence.graders[name];
    const ruling = messages.evidence.grades[grade];
    if (grader !== undefined && ruling !== undefined) {
      return messages.evidence.gradeLine(grader, ruling);
    }
  }
  return null;
}
