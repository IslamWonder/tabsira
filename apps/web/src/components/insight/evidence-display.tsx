'use client';

import { createContext, type ReactNode, useContext } from 'react';

/** What the evidence cards show beside the stored text, from the feature switches. */
export interface EvidenceDisplay {
  /** `hadith_ruling`: the first grader's ruling of the hadith's dataset; on by default. */
  hadithRuling: boolean;
  /** `quran_source_link`: «افتح في قرآنبيديا» on the verse card; off by default. */
  quranSourceLink: boolean;
}

/** The defaults of the switches, for a tree rendered without the root layout (tests, isolated views). */
export const DEFAULT_EVIDENCE_DISPLAY: EvidenceDisplay = {
  hadithRuling: true,
  quranSourceLink: false,
};

const EvidenceDisplayContext = createContext<EvidenceDisplay>(DEFAULT_EVIDENCE_DISPLAY);

/** Hands the switches read on the server, at request time, to the cards below it. */
export function EvidenceDisplayProvider({
  value,
  children,
}: Readonly<{ value: EvidenceDisplay; children: ReactNode }>) {
  return (
    <EvidenceDisplayContext.Provider value={value}>{children}</EvidenceDisplayContext.Provider>
  );
}

export function useEvidenceDisplay(): EvidenceDisplay {
  return useContext(EvidenceDisplayContext);
}
