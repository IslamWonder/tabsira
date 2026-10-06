import type { Metadata } from 'next';
import { connection } from 'next/server';
import type { CSSProperties, ReactNode } from 'react';
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
 * motion lives in the page's own <style>, with reduced motion honoured there,
 * so it needs nothing from the stylesheet either.
 */
const GOLD = 'var(--brand, #8d6e2c)';
const GLOW = 'var(--glow-gold, #ffd978)';

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

const ART: CSSProperties = { width: '168px', height: '168px', overflow: 'visible' };

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

/** Keyframes of the three scenes; every moving part carries `data-nf-motion`. */
const MOTION = `
@keyframes nf-flicker{0%,100%{opacity:.6;transform:scale(1)}40%{opacity:1;transform:scale(1.08)}70%{opacity:.75;transform:scale(.96)}}
@keyframes nf-flame{0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.12)}}
@keyframes nf-sway{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)}}
@keyframes nf-twinkle{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes nf-path{from{stroke-dashoffset:220}to{stroke-dashoffset:0}}
@keyframes nf-guide{0%,100%{opacity:.75;transform:scale(1)}50%{opacity:1;transform:scale(1.15)}}
@keyframes nf-needle{0%{transform:rotate(-70deg)}35%{transform:rotate(28deg)}60%{transform:rotate(-12deg)}80%{transform:rotate(5deg)}100%{transform:rotate(0)}}
@keyframes nf-halo{0%,100%{opacity:.35}50%{opacity:.8}}
@media (prefers-reduced-motion:reduce){[data-nf-motion]{animation:none!important}}
:root[data-motion="reduce"] [data-nf-motion]{animation:none!important}
`;

/** A soft light that fades to nothing at its edge, instead of a flat disc. */
function Glow({ id }: Readonly<{ id: string }>) {
  return (
    <defs>
      <radialGradient id={id}>
        <stop offset="0" stopColor={GLOW} stopOpacity="0.7" />
        <stop offset="1" stopColor={GLOW} stopOpacity="0" />
      </radialGradient>
    </defs>
  );
}

/** Turns about its own centre, whatever its place in the drawing. */
const ABOUT_SELF: CSSProperties = { transformBox: 'fill-box', transformOrigin: 'center' };

function Lantern() {
  return (
    <svg viewBox="0 0 160 160" style={ART} aria-hidden="true" focusable="false">
      <Glow id="nf-lantern-glow" />
      <circle
        cx="80"
        cy="90"
        r="62"
        fill="url(#nf-lantern-glow)"
        data-nf-motion=""
        style={{ ...ABOUT_SELF, opacity: 0.7, animation: 'nf-flicker 3.2s ease-in-out infinite' }}
      />
      <g
        data-nf-motion=""
        style={{
          transformBox: 'view-box',
          transformOrigin: '80px 8px',
          animation: 'nf-sway 5s ease-in-out infinite',
        }}
      >
        <path d="M80 8v22" stroke={GOLD} strokeWidth="2" />
        <circle cx="80" cy="34" r="5" fill="none" stroke={GOLD} strokeWidth="2" />
        <path d="M60 52h40l-6-12H66Z" fill={GOLD} />
        <path
          d="M62 54h36l6 50a6 6 0 0 1-6 6H62a6 6 0 0 1-6-6Z"
          fill="none"
          stroke={GOLD}
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <path d="M70 54v56M90 54v56" stroke={GOLD} strokeWidth="1.2" opacity="0.6" />
        <path
          d="M80 74c7 9 9 15 9 20a9 9 0 0 1-18 0c0-5 2-11 9-20Z"
          fill={GLOW}
          data-nf-motion=""
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'bottom',
            animation: 'nf-flame 1.6s ease-in-out infinite',
          }}
        />
        <path d="M58 112h44l-4 8H62Z" fill={GOLD} />
      </g>
    </svg>
  );
}

const STARS = [
  [24, 30, 1.6, 0],
  [44, 58, 1.2, 0.6],
  [118, 24, 1.4, 1.1],
  [140, 62, 1.8, 0.3],
  [30, 92, 1.1, 1.6],
  [132, 102, 1.2, 0.9],
  [70, 18, 1, 1.9],
] as const;

function GuidingStar() {
  return (
    <svg viewBox="0 0 160 160" style={ART} aria-hidden="true" focusable="false">
      {STARS.map(([cx, cy, r, delay]) => (
        <circle
          key={`${cx}-${cy}`}
          cx={cx}
          cy={cy}
          r={r}
          fill={GOLD}
          data-nf-motion=""
          style={{ opacity: 0.5, animation: `nf-twinkle 2.8s ease-in-out ${delay}s infinite` }}
        />
      ))}
      <path
        d="M24 150C48 120 60 104 72 92S92 68 96 52"
        fill="none"
        stroke={GOLD}
        strokeWidth="2"
        strokeDasharray="4 6"
        strokeLinecap="round"
        data-nf-motion=""
        style={{ strokeDashoffset: 0, animation: 'nf-path 2.4s ease-out both' }}
      />
      <Glow id="nf-star-glow" />
      <circle cx="98" cy="44" r="34" fill="url(#nf-star-glow)" />
      <path
        d="M98 22l5 17 17 5-17 5-5 17-5-17-17-5 17-5Z"
        fill={GOLD}
        data-nf-motion=""
        style={{ ...ABOUT_SELF, animation: 'nf-guide 3s ease-in-out infinite' }}
      />
      <path d="M10 150h140" stroke={GOLD} strokeWidth="1.5" opacity="0.5" />
    </svg>
  );
}

function Qibla() {
  return (
    <svg viewBox="0 0 160 160" style={ART} aria-hidden="true" focusable="false">
      <Glow id="nf-qibla-glow" />
      <circle
        cx="80"
        cy="80"
        r="76"
        fill="url(#nf-qibla-glow)"
        data-nf-motion=""
        style={{ opacity: 0.5, animation: 'nf-halo 3.6s ease-in-out infinite' }}
      />
      <circle cx="80" cy="80" r="58" fill="none" stroke={GOLD} strokeWidth="2" />
      {/* The eight-pointed star of the brand: two squares, one turned by 45 degrees. */}
      <rect
        x="44"
        y="44"
        width="72"
        height="72"
        fill="none"
        stroke={GOLD}
        strokeWidth="1.2"
        opacity="0.55"
      />
      <rect
        x="44"
        y="44"
        width="72"
        height="72"
        fill="none"
        stroke={GOLD}
        strokeWidth="1.2"
        opacity="0.55"
        transform="rotate(45 80 80)"
      />
      <path d="M80 14v8M80 138v8M14 80h8M138 80h8" stroke={GOLD} strokeWidth="2" />
      <g
        data-nf-motion=""
        style={{
          transformBox: 'view-box',
          transformOrigin: '80px 80px',
          animation: 'nf-needle 2.6s cubic-bezier(0.22,1,0.36,1) both',
        }}
      >
        <path d="M80 30l9 50H71Z" fill={GOLD} />
        <path d="M80 130l9-50H71Z" fill="none" stroke={GOLD} strokeWidth="1.5" />
      </g>
      <circle cx="80" cy="80" r="5" fill={GLOW} stroke={GOLD} strokeWidth="1.5" />
    </svg>
  );
}

const ART_OF: Record<NotFoundVariant, () => ReactNode> = {
  lantern: Lantern,
  star: GuidingStar,
  qibla: Qibla,
};

/** The page itself, for one variant: the scene, the words, and one way back. */
export function NotFoundScreen({ variant }: Readonly<{ variant: NotFoundVariant }>) {
  const Art = ART_OF[variant];
  const words = M.variants[variant];
  return (
    <section aria-labelledby="not-found-title" data-variant={variant} style={SCREEN}>
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: a constant above, with no input from the request or the user. */}
      <style dangerouslySetInnerHTML={{ __html: MOTION }} />
      <Art />
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
