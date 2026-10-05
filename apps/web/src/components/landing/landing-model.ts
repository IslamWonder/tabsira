import type { Route } from 'next';
import { messages } from '@/messages';

/*
 * What the landing page may announce, from the FEATURE_* flags the web server
 * reads at request time (src/config/server-env.ts). Only this public subset
 * reaches the browser: nothing administrative, no developer tool, and the
 * camera anchor (off) is never promised. A feature that is off loses its line
 * and its way in; a story with nothing left is not shown at all.
 */
export interface LandingFeatures {
  chat: boolean;
  world: boolean;
  treasure: boolean;
  social: boolean;
  atlas: boolean;
  cameraDiscovery: boolean;
  photoStorage: boolean;
  canonicalVerify: boolean;
}

export type BenefitIcon =
  | 'lens'
  | 'chat'
  | 'verify'
  | 'world'
  | 'atlas'
  | 'around'
  | 'treasure'
  | 'community'
  | 'photos';

export interface Benefit {
  icon: BenefitIcon;
  title: string;
  text: string;
}

/** Where a story leads: a page of the app, or the example on this page. */
export type StoryAction =
  | { kind: 'link'; href: Route; label: string; icon: BenefitIcon }
  | { kind: 'example'; label: string; icon: BenefitIcon };

export interface Story {
  id: 'meaning' | 'world' | 'community';
  image: { src: string; alt: string };
  tag: string;
  title: string;
  lead: string;
  benefits: Benefit[];
  action: StoryAction | null;
}

const F = messages.landing.features;
const NAV = messages.landing.nav;

/**
 * The landing page's own links, its sections, for a visitor: the top bar shows them on
 * the home page. The app's sections stay in the phone's bar, the cards and every other page.
 */
export const LANDING_LINKS: readonly { href: Route; label: string }[] = [
  { href: '/', label: NAV.home },
  { href: '/#how' as Route, label: NAV.how },
  { href: '/#features' as Route, label: NAV.features },
  { href: '/#example' as Route, label: NAV.example },
];

function benefit(icon: BenefitIcon, text: { title: string; text: string }, on = true): Benefit[] {
  return on ? [{ icon, ...text }] : [];
}

function meaning(features: LandingFeatures): Story {
  return {
    id: 'meaning',
    image: { src: '/landing/meaning-dialogue.webp', alt: F.meaning.alt },
    tag: F.meaning.tag,
    title: F.meaning.title,
    lead: F.meaning.lead,
    benefits: [
      ...benefit('lens', F.meaning.lens),
      ...benefit('chat', F.meaning.chat, features.chat),
      ...benefit('verify', F.meaning.verify, features.canonicalVerify),
    ],
    // The core journey: always there, whatever is switched off.
    action: { kind: 'example', label: F.meaning.action, icon: 'lens' },
  };
}

function world(features: LandingFeatures): Story {
  let action: StoryAction | null = null;
  if (features.atlas) {
    action = { kind: 'link', href: '/atlas', label: F.world.openAtlas, icon: 'atlas' };
  } else if (features.world) {
    action = { kind: 'link', href: '/world', label: F.world.openWorld, icon: 'world' };
  }
  return {
    id: 'world',
    image: { src: '/landing/world-atlas.webp', alt: F.world.alt },
    tag: F.world.tag,
    title: F.world.title,
    lead: F.world.lead,
    benefits: [
      ...benefit('world', F.world.world, features.world),
      ...benefit('atlas', F.world.atlas, features.atlas),
      ...benefit('around', F.world.around, features.atlas && features.cameraDiscovery),
    ],
    action,
  };
}

function community(features: LandingFeatures): Story {
  let action: StoryAction | null = null;
  if (features.social) {
    action = {
      kind: 'link',
      href: '/community',
      label: F.community.openCommunity,
      icon: 'community',
    };
  } else if (features.world) {
    action = { kind: 'link', href: '/world', label: F.community.openWorld, icon: 'world' };
  }
  return {
    id: 'community',
    image: { src: '/landing/treasure-community.webp', alt: F.community.alt },
    tag: F.community.tag,
    title: F.community.title,
    lead: F.community.lead,
    benefits: [
      // The treasure waits in the world's places (v2 §17): without the world there is none.
      ...benefit('treasure', F.community.treasure, features.treasure && features.world),
      ...benefit('community', F.community.social, features.social),
      ...benefit('photos', F.community.photos, features.photoStorage),
    ],
    action,
  };
}

/** The three stories of the features section, each with only what is switched on; none left empty. */
export function featureStories(features: LandingFeatures): Story[] {
  return [meaning(features), world(features), community(features)].filter(
    (story) => story.benefits.length > 0
  );
}
