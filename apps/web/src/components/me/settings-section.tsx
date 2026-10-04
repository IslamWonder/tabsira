'use client';

import type { ConsentSwitch, Profile } from '@/account/profile';
import { GENDER_CHOICES, RELIGION_CHOICES } from '@/components/account/profile-options';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { MotionSwitch } from '@/components/ui/motion-switch';
import { SwitchRow } from '@/components/ui/switch-row';
import { ThemeSwitcher } from '@/components/ui/theme-switcher';
import { messages } from '@/messages';
import { MeSection, SubHeading } from './me-section';
import { SaveStatus, useSaveState } from './save-status';
import type { ProfileEditor } from './use-profile';

const S = messages.settings;
const P = messages.profile;

function AccountSettings({
  profile,
  save,
  setSwitch,
}: {
  profile: Profile;
  save: ProfileEditor['save'];
  setSwitch: ProfileEditor['setSwitch'];
}) {
  const { state, run, busy } = useSaveState();
  const toggle = (kind: ConsentSwitch, on: boolean) => run(() => setSwitch(kind, on));
  const under13 = profile.age_range === 'under_13';
  return (
    <div className="flex flex-col gap-5">
      <SwitchRow
        label={S.personalization.label}
        hint={S.personalization.hint}
        checked={profile.personalization_enabled}
        onChange={(on) => toggle('personalization', on)}
        busy={busy}
      />
      <SwitchRow
        label={S.memory.label}
        hint={S.memory.hint}
        checked={profile.memory_enabled}
        onChange={(on) => toggle('memory', on)}
        busy={busy}
      />
      <SwitchRow
        label={S.photos.label}
        hint={under13 ? `${S.photos.hint} ${S.photos.under13}` : S.photos.hint}
        checked={profile.photo_storage_consent}
        // A declared age under 13 rules it out (master prompt v2 §5); the API refuses it too.
        disabled={under13 && !profile.photo_storage_consent}
        onChange={(on) => toggle('photo_storage', on)}
        busy={busy}
      />
      {/* Religion and gender are asked here only, never in the first questions (v2 §5). */}
      <ChoiceGroup
        legend={P.religion.label}
        hint={P.religion.hint}
        options={RELIGION_CHOICES}
        value={profile.religious_background}
        onChange={(religious_background) => run(() => save({ religious_background }))}
      />
      <ChoiceGroup
        legend={P.gender.label}
        hint={P.gender.hint}
        options={GENDER_CHOICES}
        value={profile.gender}
        onChange={(gender) => run(() => save({ gender }))}
      />
      <SaveStatus state={state} />
    </div>
  );
}

/**
 * The settings (tajriba S13): what this device shows (theme, decorative
 * motion) for everyone, then what the account keeps (personalisation, memory,
 * photo storage, and the two private answers) once signed in. Sound has no
 * switch until there is sound (owner, 4 October 2026).
 */
export function SettingsSection({
  editor,
  signedIn,
}: {
  editor: ProfileEditor;
  signedIn: boolean;
}) {
  const { load } = editor;
  return (
    <MeSection id="settings" title={messages.pages.me.sections.settings}>
      <SubHeading>{S.device}</SubHeading>
      <ThemeSwitcher />
      <MotionSwitch />
      <SubHeading>{S.account}</SubHeading>
      {signedIn ? null : (
        <p className="m-0 text-fg-soft">{messages.pages.me.guest.accountSettings}</p>
      )}
      {load.status === 'loading' ? (
        <p role="status" className="m-0 text-fg-muted">
          {messages.pages.me.loading}
        </p>
      ) : null}
      {load.status === 'failed' ? (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="m-0 text-danger">{messages.errors.server}</p>
          <button
            type="button"
            onClick={editor.reload}
            className="inline-flex min-h-12 items-center text-link"
          >
            {messages.pages.me.retry}
          </button>
        </div>
      ) : null}
      {load.status === 'ready' ? (
        <AccountSettings profile={load.profile} save={editor.save} setSwitch={editor.setSwitch} />
      ) : null}
    </MeSection>
  );
}
