'use client';

import { useState } from 'react';
import { useSession } from '@/account/session';
import { SettingsLayout } from '@/components/layout/layouts';
import { messages } from '@/messages';
import { AboutSection } from './about-section';
import { AccountSection } from './account-section';
import { CookiesSection } from './cookies-section';
import { DataSection } from './data-section';
import { PracticeSection } from './practice-section';
import { SettingsSection } from './settings-section';
import { useProfile } from './use-profile';

const M = messages.pages.me;
type SectionId = keyof typeof M.sections;

/**
 * The profile page (S13): the account, the optional answers, the settings, practice,
 * the data and the cookie choice, one panel each. A guest sees the device
 * settings and the cookie choice, and what an account adds. Every change is
 * saved at once and confirmed only once the API kept it.
 */
export function MeScreen() {
  const session = useSession();
  const signedIn = session.status === 'signed-in';
  const editor = useProfile(signedIn);
  const [notice, setNotice] = useState<string | null>(null);
  const sections: SectionId[] = signedIn
    ? ['account', 'about', 'settings', 'practice', 'data', 'cookies']
    : ['account', 'settings', 'practice', 'cookies'];

  return (
    <SettingsLayout
      className="flex flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-4 tablet:pb-8"
      nav={
        <nav aria-label={M.sectionsLabel}>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {sections.map((section) => (
              <li key={section}>
                <a
                  href={`#${section}`}
                  className="flex min-h-12 items-center rounded-[var(--radius-card)] px-4 text-fg-soft transition-colors duration-200 hover:bg-surface hover:text-fg"
                >
                  {M.sections[section]}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      }
    >
      <h1 className="m-0 font-bold font-display text-[2rem] text-fg">{M.title}</h1>
      <AccountSection
        session={session}
        notice={notice}
        onSignedOut={() => setNotice(messages.auth.signOut.done)}
      />
      {signedIn && editor.load.status === 'ready' ? (
        <AboutSection profile={editor.load.profile} save={editor.save} />
      ) : null}
      <SettingsSection editor={editor} signedIn={signedIn} />
      <PracticeSection />
      {signedIn ? (
        <DataSection onDeleted={() => setNotice(messages.pages.me.delete.deleted)} />
      ) : null}
      <CookiesSection />
    </SettingsLayout>
  );
}
