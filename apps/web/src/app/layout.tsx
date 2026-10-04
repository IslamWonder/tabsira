import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { AppNav } from '@/components/app/app-nav';
import { ServiceWorkerRegister } from '@/components/app/service-worker-register';
import { SkipLink } from '@/components/app/skip-link';
import { StageBackdrop } from '@/components/app/stage-backdrop';
import { ThemeSync } from '@/components/app/theme-sync';
import { TopBar } from '@/components/app/top-bar';
import { BurstLayer } from '@/components/fx/burst-layer';
import { FocusCursor } from '@/components/fx/focus-cursor';
import { VictoryLayer } from '@/components/fx/victory-layer';
import { fontVariables } from '@/fonts';
import { siteOrigin } from '@/lib/site';
import { ar } from '@/messages/ar';
import { PREFERENCES_INIT_SCRIPT } from '@/preferences/init-script';
import { THEME_BACKGROUND } from '@/theme/colors';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: siteOrigin(),
  title: { default: ar.meta.title, template: ar.meta.titleTemplate },
  description: ar.meta.description,
  applicationName: ar.meta.siteName,
  alternates: { canonical: '/' },
  formatDetection: { telephone: false, email: false, address: false },
  appleWebApp: { capable: true, title: ar.meta.siteName, statusBarStyle: 'black-translucent' },
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '16x16 32x32 48x48' },
      { url: '/icons/icon-192.png', type: 'image/png', sizes: '192x192' },
    ],
    apple: { url: '/icons/apple-touch-icon.png', sizes: '180x180' },
  },
  openGraph: {
    type: 'website',
    locale: 'ar',
    siteName: ar.meta.siteName,
    title: ar.meta.title,
    description: ar.meta.description,
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

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The inline script may set data-theme and data-motion before React hydrates; those may differ.
    <html lang="ar" dir="rtl" className={fontVariables} suppressHydrationWarning>
      <head>
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: a constant written in src/preferences/init-script.ts, with no input from the request or the user; it must run before the first paint. */}
        <script dangerouslySetInnerHTML={{ __html: PREFERENCES_INIT_SCRIPT }} />
      </head>
      <body className="antialiased">
        <SkipLink />
        <StageBackdrop />
        <TopBar />
        <main id="main" tabIndex={-1} className="outline-none">
          {children}
        </main>
        <AppNav />
        <BurstLayer />
        <VictoryLayer />
        <FocusCursor />
        <ThemeSync />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
