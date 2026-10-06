import type { Metadata } from 'next';
import { connection } from 'next/server';
import type { CSSProperties } from 'react';
import { GuideScene } from '@/components/ui/guide-scene';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.pages.notFound.title,
  robots: { index: false, follow: false },
};

const M = messages.pages.notFound;

export type NotFoundVariant = keyof typeof M.variants;
export const NOT_FOUND_VARIANTS = Object.keys(M.variants) as NotFoundVariant[];

/*
 * Inline styles and system fonts only (docs/SEO.md §1): a missing page must
 * still read well when the stylesheet or a font fails to load. The theme's
 * variables are used when present; the fallbacks are the light theme. The
 * scene (components/ui/guide-scene.tsx) carries its own motion the same way.
 */
const GOLD = 'var(--brand, #8d6e2c)';

const SCREEN: CSSProperties = {
  boxSizing: 'border-box',
  minHeight: '70vh',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '18px',
  padding: '48px 24px',
  textAlign: 'center',
  color: 'var(--text, #16302a)',
  background: 'var(--bg, #f6faf7)',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", Tahoma, Arial, sans-serif',
};

const CODE: CSSProperties = {
  margin: 0,
  padding: '4px 14px',
  borderRadius: '999px',
  border: `1px solid ${GOLD}`,
  color: GOLD,
  fontSize: '0.8125rem',
  letterSpacing: '0.04em',
};

const TITLE: CSSProperties = { margin: 0, fontSize: '1.75rem', lineHeight: 1.45, color: GOLD };

const TEXT: CSSProperties = {
  margin: 0,
  maxWidth: '30rem',
  lineHeight: 2,
  color: 'var(--text-soft, #34544b)',
};

const ACTION: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: '48px',
  padding: '0 24px',
  borderRadius: '12px',
  fontWeight: 700,
  textDecoration: 'none',
  color: 'var(--on-primary, #ffffff)',
  background: 'var(--primary, #0f4c3a)',
};

/** The page itself, for one variant: the scene, the words, and one way back. */
export function NotFoundScreen({ variant }: Readonly<{ variant: NotFoundVariant }>) {
  const words = M.variants[variant];
  return (
    <section aria-labelledby="not-found-title" data-variant={variant} style={SCREEN}>
      <GuideScene scene={variant} />
      <p style={CODE}>{M.code}</p>
      <h1 id="not-found-title" style={TITLE}>
        {words.title}
      </h1>
      <p style={TEXT}>{words.body}</p>
      <a href="/" style={ACTION}>
        {M.action}
      </a>
    </section>
  );
}

/** One of the three, chosen afresh at each request. */
export default async function NotFound() {
  await connection();
  const pick = Math.floor(Math.random() * NOT_FOUND_VARIANTS.length);
  return <NotFoundScreen variant={NOT_FOUND_VARIANTS[pick] as NotFoundVariant} />;
}
