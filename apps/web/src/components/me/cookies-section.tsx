'use client';

import { Button } from '@/components/ui/button';
import { OPTIONAL_CATEGORIES } from '@/consent/contract';
import { openConsentSettings, useConsent } from '@/consent/store';
import { formatWhen } from '@/lib/dates';
import { messages } from '@/messages';
import { MeSection } from './me-section';

const C = messages.consent;

/** The cookie choice as it stands, and the way to change it (owner decision 32). */
export function CookiesSection() {
  const { consent } = useConsent();
  return (
    <MeSection
      id="cookies"
      title={messages.pages.me.sections.cookies}
      description={messages.pages.me.cookies.body}
    >
      {consent.status === 'decided' ? (
        <div className="flex flex-col gap-2">
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            <li className="flex justify-between gap-4 text-fg">
              <span>{C.categoryNames.necessary}</span>
              <span className="text-fg-soft">{C.always}</span>
            </li>
            {OPTIONAL_CATEGORIES.map((category) => (
              <li key={category} className="flex justify-between gap-4 text-fg">
                <span>{C.categoryNames[category]}</span>
                <span className="text-fg-soft">
                  {consent.record.categories[category] ? C.allowed : C.notAllowed}
                </span>
              </li>
            ))}
          </ul>
          <p className="m-0 text-fg-muted text-sm">
            {C.decidedOn(formatWhen(consent.record.decided_at))}
          </p>
        </div>
      ) : (
        <p className="m-0 text-fg-soft">{C.undecided}</p>
      )}
      <div>
        <Button variant="secondary" aria-haspopup="dialog" onClick={openConsentSettings}>
          {C.change}
        </Button>
      </div>
    </MeSection>
  );
}
