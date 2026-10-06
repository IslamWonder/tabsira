'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { type CountryOption, loadCountries } from '@/account/countries';
import type { ConsentSwitch, Profile } from '@/account/profile';
import { GENDER_CHOICES, RELIGION_CHOICES } from '@/components/account/profile-options';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { MotionSwitch } from '@/components/ui/motion-switch';
import { SoundSwitch } from '@/components/ui/sound-switch';
import { SwitchRow } from '@/components/ui/switch-row';
import { ThemeSwitcher } from '@/components/ui/theme-switcher';
import { messages } from '@/messages';
import { MeSection } from './me-section';
import { SaveStatus, useSaveState } from './save-status';
import type { ProfileEditor } from './use-profile';

const S = messages.settings;
const P = messages.profile;

type CountriesLoad =
  | { status: 'loading' | 'failed' }
  | { status: 'ready'; countries: readonly CountryOption[] };

/** The GeoNames country list, read when the settings open; a failure offers a retry. */
function useCountries(): { load: CountriesLoad; retry: () => void } {
  const [load, setLoad] = useState<CountriesLoad>({ status: 'loading' });
  // An answer that arrives after the settings closed is dropped.
  const live = useRef(true);
  const read = useCallback(() => {
    setLoad({ status: 'loading' });
    void loadCountries().then((result) => {
      if (live.current) {
        setLoad(result.ok ? { status: 'ready', countries: result.data } : { status: 'failed' });
      }
    });
  }, []);
  useEffect(() => {
    live.current = true;
    read();
    return () => {
      live.current = false;
    };
  }, [read]);
  return { load, retry: read };
}

/**
 * The optional country (decision 67): a native select, which types ahead to a name, with
 * the empty answer first; the switch that shows it publicly is separate and off until turned on.
 */
function CountrySetting({
  profile,
  onCountry,
  toggle,
  busy,
}: {
  profile: Profile;
  onCountry: (country: string | null) => void;
  toggle: (kind: ConsentSwitch, on: boolean) => void;
  busy: boolean;
}) {
  const selectId = useId();
  const hintId = useId();
  const { load, retry } = useCountries();
  const under13 = profile.age_range === 'under_13';
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label htmlFor={selectId} className="font-semibold text-fg text-lg">
          {S.country.label}
        </label>
        <p id={hintId} className="m-0 text-fg-muted text-sm leading-[1.8]">
          {S.country.hint}
        </p>
        {load.status === 'loading' ? (
          <p role="status" className="m-0 text-fg-muted">
            {S.country.loading}
          </p>
        ) : null}
        {load.status === 'failed' ? (
          <div role="alert" className="flex flex-col items-start gap-2">
            <p className="m-0 text-danger">{S.country.failed}</p>
            <button
              type="button"
              onClick={retry}
              className="inline-flex min-h-12 items-center text-link"
            >
              {S.country.retry}
            </button>
          </div>
        ) : null}
        {load.status === 'ready' ? (
          <select
            id={selectId}
            aria-describedby={hintId}
            value={profile.country ?? ''}
            onChange={(event) => onCountry(event.target.value || null)}
            className="min-h-12 w-full rounded-[var(--radius-card)] border border-field bg-surface px-4 text-fg"
          >
            <option value="">{S.country.none}</option>
            {load.countries.map((country) => (
              <option key={country.code} value={country.code}>
                {country.name}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <SwitchRow
        label={S.showCountry.label}
        hint={under13 ? `${S.showCountry.hint} ${S.showCountry.under13}` : S.showCountry.hint}
        checked={profile.show_country}
        // A declared age under 13 rules it out, as for the full name; the API refuses it too.
        disabled={under13 && !profile.show_country}
        onChange={(on) => toggle('public_country', on)}
        busy={busy}
      />
    </div>
  );
}

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
      <CountrySetting
        profile={profile}
        onCountry={(country) => run(() => save({ country }))}
        toggle={toggle}
        busy={busy}
      />
      <SaveStatus state={state} />
    </div>
  );
}

/**
 * What this device shows, for everyone, signed in or not (tajriba S13): the
 * theme, the decorative motion and the sound effect. Kept on the device only.
 */
export function AppearanceSection() {
  return (
    <MeSection
      id="appearance"
      title={messages.pages.me.sections.appearance}
      description={messages.pages.me.summaries.appearance}
    >
      <ThemeSwitcher />
      <MotionSwitch />
      <SoundSwitch />
    </MeSection>
  );
}

/**
 * What the account keeps about how it serves the reader (tajriba S13):
 * personalisation, memory, photo storage and the two private answers. A guest
 * is told these come with an account.
 */
export function PersonalizationSection({
  editor,
  signedIn,
}: {
  editor: ProfileEditor;
  signedIn: boolean;
}) {
  const { load } = editor;
  return (
    <MeSection
      id="personalization"
      title={messages.pages.me.sections.personalization}
      description={messages.pages.me.summaries.personalization}
    >
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
