import { OnwardIcon } from '@/components/icons';
import { type EmblemName, EmblemTile } from '@/components/ui/emblem';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

const M = messages.pages.me;

export type SectionId = keyof typeof M.sections;
export type GroupId = keyof typeof M.groups;

/** Each section's emblem (src/components/ui/emblem-data.ts). */
export const SECTION_EMBLEMS: Record<SectionId, EmblemName> = {
  account: 'me_account',
  about: 'me_about',
  identity: 'me_identity',
  appearance: 'me_appearance',
  personalization: 'me_personalization',
  practice: 'me_practice',
  app: 'me_app',
  data: 'me_data',
  cookies: 'me_cookies',
};

export interface MenuGroup {
  id: GroupId;
  sections: SectionId[];
}

export interface MeMenuProps {
  groups: readonly MenuGroup[];
  /** The section shown beside the menu, marked as the current one. */
  current: SectionId | null;
  /** The phone's hub: each entry says in one line what it holds. */
  withSummaries?: boolean;
  /** A guest's account entry invites to sign in rather than describing an account. */
  signedIn: boolean;
}

/**
 * The menu of the profile page (/me), the way a phone's own settings are laid out (Jakob's
 * law): a few short groups (Hick's law, Miller's law), each entry with its
 * emblem so it is found at a glance, its name, and on a phone one line on what
 * it holds; the entry shown beside the menu is marked as the current page.
 */
export function MeMenu({
  groups,
  current,
  withSummaries = false,
  signedIn,
}: Readonly<MeMenuProps>) {
  return (
    <nav aria-label={M.sectionsLabel} className="flex flex-col gap-5">
      {groups.map((group) => (
        <section key={group.id} aria-label={M.groups[group.id]} className="flex flex-col gap-1.5">
          <h2 className="m-0 px-1 font-semibold text-[0.8125rem] text-[var(--landing-gold)]">
            {M.groups[group.id]}
          </h2>
          <ul
            className={cx(
              'm-0 flex list-none flex-col p-0',
              withSummaries && 'glass overflow-hidden rounded-[var(--radius-panel)]'
            )}
          >
            {group.sections.map((section, index) => (
              <li
                key={section}
                className={cx(withSummaries && index > 0 && 'border-line border-t')}
              >
                <a
                  href={`#${section}`}
                  aria-current={section === current ? 'page' : undefined}
                  className={cx(
                    'flex min-h-14 items-center gap-3.5 px-3 py-2.5 transition-colors duration-200',
                    withSummaries
                      ? 'hover:bg-surface'
                      : 'rounded-[var(--radius-card)] hover:bg-surface aria-[current=page]:bg-[var(--chip-primary-bg)]'
                  )}
                >
                  <EmblemTile name={SECTION_EMBLEMS[section]} size="sm" />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="font-semibold text-fg">{M.sections[section]}</span>
                    {withSummaries ? (
                      <span className="text-[0.8125rem] text-fg-muted leading-relaxed">
                        {section === 'account' && !signedIn
                          ? M.summaries.accountGuest
                          : M.summaries[section]}
                      </span>
                    ) : null}
                  </span>
                  {withSummaries ? (
                    <OnwardIcon width="18" height="18" className="shrink-0 text-fg-muted" />
                  ) : null}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}
