import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { CLARITY_MASK } from '@/analytics/clarity';
import { LegalGate } from '@/components/account/legal-gate';
import { AccountPreferencesSync } from '@/components/app/account-preferences-sync';
import { AppNav } from '@/components/app/app-nav';
import { InstallOffer } from '@/components/app/install-offer';
import { PageShell } from '@/components/app/page-shell';
import { ServiceWorkerRegister } from '@/components/app/service-worker-register';
import { SiteFooter } from '@/components/app/site-footer';
import { SkipLink } from '@/components/app/skip-link';
import { StageBackdrop } from '@/components/app/stage-backdrop';
import { ThemeSync } from '@/components/app/theme-sync';
import { TopBar } from '@/components/app/top-bar';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { AnalyticsTags } from '@/components/consent/analytics-tags';
import { consentModeDefaults } from '@/components/consent/consent-mode-defaults';
import { ConsentScreen } from '@/components/consent/consent-screen';
import { BurstLayer } from '@/components/fx/burst-layer';
import { FocusCursor } from '@/components/fx/focus-cursor';
import { VictoryLayer } from '@/components/fx/victory-layer';
import { clarityProjectId, gaMeasurementId } from '@/config/server-env';
import { serverConsent } from '@/consent/server';
import { fontVariables } from '@/fonts';
import { SHARE_IMAGE } from '@/lib/seo';
import { siteOrigin } from '@/lib/site';
import { messages, siteLanguage } from '@/messages';
import { PREFERENCES_INIT_SCRIPT } from '@/preferences/init-script';
import { INSTALL_CAPTURE_SCRIPT } from '@/pwa/install';
import { THEME_BACKGROUND } from '@/theme/colors';

import './globals.css';

export const metadata: Metadata = {
  metadataBase: siteOrigin(),
  title: { default: messages.meta.title, template: messages.meta.titleTemplate },
  description: messages.meta.description,
  applicationName: messages.meta.siteName,
  // No canonical here: it would be inherited by any page that forgets its own (see src/lib/seo.ts).
  formatDetection: { telephone: false, email: false, address: false },
  appleWebApp: {
    capable: true,
    title: messages.meta.siteName,
    statusBarStyle: 'black-translucent',
  },
  // Every icon is drawn from the logo in brand/ by scripts/make-icons.mjs.
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '16x16 32x32 48x48' },
      { url: '/icon.svg', type: 'image/svg+xml', sizes: 'any' },
      { url: '/icons/icon-192.png', type: 'image/png', sizes: '192x192' },
    ],
    apple: { url: '/icons/apple-icon.png', sizes: '180x180' },
  },
  other: {
    'msapplication-config': '/browserconfig.xml',
    'msapplication-TileColor': THEME_BACKGROUND.dark,
  },
  openGraph: {
    type: 'website',
    locale: siteLanguage.ogLocale,
    siteName: messages.meta.siteName,
    title: messages.meta.title,
    description: messages.meta.description,
    images: [SHARE_IMAGE],
  },
  twitter: {
    card: 'summary_large_image',
    title: messages.meta.title,
    description: messages.meta.description,
    images: [SHARE_IMAGE],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // No maximum scale: zooming stays possible (WCAG 1.4.4).
  viewportFit: 'cover',
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: THEME_BACKGROUND.light },
    { media: '(prefers-color-scheme: dark)', color: THEME_BACKGROUND.dark },
  ],
};

/**
 * Rendered per request: the analytics configuration is read on the server at
 * request time (owner decision 28), so no build ever fixes it.
 */
export default async function RootLayout({ children }: { children: ReactNode }) {
  const [consentDefaults, consent] = await Promise.all([consentModeDefaults(), serverConsent()]);
  return (
    // The inline script may set data-theme and data-motion before React hydrates; those may differ.
    <html
      lang={siteLanguage.tag}
      dir={siteLanguage.dir}
      className={fontVariables}
      suppressHydrationWarning
    >
      <head>
        {/* First of all scripts: Consent Mode v2 defaults, all denied, when GA is configured. */}
        {consentDefaults}
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: a constant written in src/preferences/init-script.ts, with no input from the request or the user; it must run before the first paint. */}
        <script dangerouslySetInnerHTML={{ __html: PREFERENCES_INIT_SCRIPT }} />
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: a constant written in src/pwa/install.ts, with no input from the request or the user; it must listen before hydration. */}
        <script dangerouslySetInnerHTML={{ __html: INSTALL_CAPTURE_SCRIPT }} />
      </head>
      {/* Clarity masks everything under this attribute: no typed text, scripture or user text is recorded. */}
      <body className="antialiased" {...CLARITY_MASK}>
        <PageShell consent={consent}>
          {/* Every capture button (nav.captureScene), in the bars or on a page, opens the same camera and send. */}
          <CaptureProvider>
            <SkipLink />
            <StageBackdrop />
            <TopBar />
            <main id="main" tabIndex={-1} className="outline-none">
              {children}
            </main>
            <SiteFooter />
            <AppNav />
          </CaptureProvider>
        </PageShell>
        {/* In the first paint when a choice is needed: no flash of the page before it. */}
        <ConsentScreen initial={consent} />
        <LegalGate />
        <BurstLayer />
        <VictoryLayer />
        <FocusCursor />
        <AnalyticsTags gaId={gaMeasurementId()} clarityId={clarityProjectId()} />
        <ThemeSync />
        <AccountPreferencesSync />
        <ServiceWorkerRegister />
        <InstallOffer />
      </body>
    </html>
  );
}
