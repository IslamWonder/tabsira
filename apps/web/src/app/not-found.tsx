import type { Metadata } from 'next';
import type { CSSProperties } from 'react';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.pages.notFound.title,
  robots: { index: false, follow: false },
};

/*
 * Inline styles and system fonts only (docs/SEO.md §1): a missing page must
 * still read well when the stylesheet or a font fails to load. The theme's
 * variables are used when present; the fallbacks are the light theme.
 */
const SCREEN: CSSProperties = {
  boxSizing: 'border-box',
  minHeight: '60vh',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '16px',
  padding: '40px 24px',
  textAlign: 'center',
  color: 'var(--text, #16302a)',
  background: 'var(--bg, #f6faf7)',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", Tahoma, Arial, sans-serif',
};

const TITLE: CSSProperties = { margin: 0, fontSize: '1.75rem', lineHeight: 1.4 };

const TEXT: CSSProperties = { margin: 0, maxWidth: '28rem', lineHeight: 1.9 };

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

export default function NotFound() {
  return (
    <section aria-labelledby="not-found-title" style={SCREEN}>
      <h1 id="not-found-title" style={TITLE}>
        {messages.pages.notFound.title}
      </h1>
      <p style={TEXT}>{messages.pages.notFound.description}</p>
      <a href="/" style={ACTION}>
        {messages.pages.notFound.action}
      </a>
    </section>
  );
}
