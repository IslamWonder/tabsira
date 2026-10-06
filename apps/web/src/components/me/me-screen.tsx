'use client';

import { type ReactNode, useEffect, useRef, useState } from 'react';
import { useSession } from '@/account/session';
import { IdentitySection } from '@/components/community/identity-section';
import { BackIcon } from '@/components/icons';
import { SettingsLayout } from '@/components/layout/layouts';
import { messages } from '@/messages';
import { AboutSection } from './about-section';
import { AccountSection } from './account-section';
import { AppSection } from './app-section';
import { CookiesSection } from './cookies-section';
import { DataSection } from './data-section';
import { MeMenu, type MenuGroup, type SectionId } from './me-menu';
import { PracticeSection } from './practice-section';
import { AppearanceSection, PersonalizationSection } from './settings-section';
import { useProfile } from './use-profile';
import { useOpenSection } from './use-section';

const M = messages.pages.me;

/** The reader's sections, in three short groups; a guest's are fewer. */
function groupsFor(signedIn: boolean): MenuGroup[] {
  return [
    { id: 'you', sections: signedIn ? ['account', 'about', 'identity'] : ['account'] },
    { id: 'experience', sections: ['appearance', 'personalization', 'practice', 'app'] },
    { id: 'privacy', sections: signedIn ? ['data', 'cookies'] : ['cookies'] },
  ];
}

/**
 * The profile page (S13), organised the way a phone's own settings are: on a
 * phone, a menu of short groups, each entry with its emblem and one line on
 * what it holds, and one section at a time behind it with a way back; from
 * tablet up the same menu stays beside the section shown, the first one by
 * default. The open section is in the address (`/me#data`), so links, the back
 * button and a shared address all work. Every change inside a section is
 * saved at once and confirmed only once the API kept it.
 */
export function MeScreen() {
  const session = useSession();
  const signedIn = session.status === 'signed-in';
  const editor = useProfile(signedIn);
  const [notice, setNotice] = useState<string | null>(null);
  const groups = groupsFor(signedIn);
  const sections = groups.flatMap((group) => group.sections);
  const { open, close } = useOpenSection(sections);
  const shown: SectionId = open ?? (sections[0] as SectionId);

  // A section opened from the menu takes the focus, so reading starts there.
  const opened = useRef(open);
  useEffect(() => {
    if (open !== null && open !== opened.current) {
      document.getElementById(open)?.focus();
    }
    opened.current = open;
  }, [open]);

  const section: Record<SectionId, ReactNode> = {
    account: (
      <AccountSection
        session={session}
        notice={notice}
        onSignedOut={() => setNotice(messages.auth.signOut.done)}
      />
    ),
    about:
      editor.load.status === 'ready' ? (
        <AboutSection profile={editor.load.profile} save={editor.save} />
      ) : (
        <p role="status" className="m-0 text-fg-muted">
          {M.loading}
        </p>
      ),
    identity: <IdentitySection />,
    appearance: <AppearanceSection />,
    personalization: <PersonalizationSection editor={editor} signedIn={signedIn} />,
    practice: <PracticeSection />,
    app: <AppSection />,
    data: <DataSection onDeleted={() => setNotice(messages.pages.me.delete.deleted)} />,
    cookies: <CookiesSection />,
  };

  return (
    <SettingsLayout
      className="flex flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-4 tablet:pb-8"
      nav={<MeMenu groups={groups} current={shown} signedIn={signedIn} />}
    >
      <header className="flex items-center gap-2">
        {open === null ? null : (
          <button
            type="button"
            onClick={close}
            aria-label={M.back}
            className="glass inline-flex size-12 shrink-0 items-center justify-center rounded-full text-fg tablet:hidden"
          >
            <BackIcon />
          </button>
        )}
        <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
          {M.title}
        </h1>
      </header>
      {open === null ? (
        <div className="flex flex-col gap-5 tablet:hidden">
          <p className="m-0 text-fg-soft leading-[1.85]">{M.description}</p>
          <MeMenu groups={groups} current={null} withSummaries signedIn={signedIn} />
        </div>
      ) : null}
      <div className={open === null ? 'hidden tablet:block' : undefined}>{section[shown]}</div>
    </SettingsLayout>
  );
}
