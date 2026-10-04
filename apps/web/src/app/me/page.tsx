import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { ProfileIcon } from '@/components/icons';
import { SettingsLayout } from '@/components/layout/layouts';
import { GlassPanel } from '@/components/ui/glass-panel';
import { MotionSwitch } from '@/components/ui/motion-switch';
import { ThemeSwitcher } from '@/components/ui/theme-switcher';
import { ar } from '@/messages/ar';

export const metadata: Metadata = {
  title: ar.nav.me,
  alternates: { canonical: '/me' },
  robots: { index: false, follow: false },
};

const SECTIONS = ar.pages.me.sections;

/** The account part is not built yet; the appearance and motion choices already work, on this device. */
export default function MePage() {
  return (
    <SettingsLayout
      className="flex flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-nav tablet:pb-8"
      nav={
        <nav aria-label={ar.pages.me.sectionsLabel}>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {(['appearance', 'motion', 'account'] as const).map((section) => (
              <li key={section}>
                <a
                  href={`#${section}`}
                  className="flex min-h-12 items-center rounded-[var(--radius-card)] px-4 text-fg-soft transition-colors duration-200 hover:bg-surface hover:text-fg"
                >
                  {SECTIONS[section]}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      }
    >
      <h1 className="m-0 font-bold text-[2rem] text-fg">{ar.pages.me.title}</h1>
      <GlassPanel as="section" id="appearance" aria-label={SECTIONS.appearance}>
        <ThemeSwitcher />
      </GlassPanel>
      <GlassPanel as="section" id="motion" aria-label={SECTIONS.motion}>
        <MotionSwitch />
      </GlassPanel>
      <GlassPanel as="section" id="account" aria-label={SECTIONS.account}>
        <ComingSoon
          headingLevel={2}
          align="start"
          emblem={false}
          icon={<ProfileIcon width="28" height="28" />}
          title={SECTIONS.account}
          description={ar.pages.me.description}
        />
      </GlassPanel>
    </SettingsLayout>
  );
}
