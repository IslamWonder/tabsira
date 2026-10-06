'use client';

import Image from 'next/image';
import Link from 'next/link';
import { Fragment, type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { tutorialOffered, useSession } from '@/account/session';
import { LogoMark } from '@/components/brand/logo';
import { useCapture } from '@/components/capture/capture-provider';
import { revealDelay, useReveal } from '@/components/fx/use-reveal';
import { CameraIcon, MenuIcon, OnwardArrowIcon, OnwardIcon, ShieldIcon } from '@/components/icons';
import { CaptureCard } from '@/components/scene/capture-card';
import { Emblem, type EmblemName, EmblemTile } from '@/components/ui/emblem';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { HeroAtmosphere, KhatamStar } from './hero-atmosphere';
import { InsightExample } from './insight-example';
import {
  type BenefitIcon,
  featureStories,
  LANDING_LINKS,
  type LandingFeatures,
  type Story,
} from './landing-model';
import { PhonePreview } from './phone-preview';

const L = messages.landing;

/** Each benefit's emblem (src/components/ui/emblem-data.ts). */
const BENEFIT_EMBLEMS: Record<BenefitIcon, EmblemName> = {
  lens: 'camera',
  chat: 'chat',
  verify: 'verify',
  world: 'world',
  atlas: 'atlas',
  around: 'around',
  treasure: 'treasure',
  community: 'community',
  photos: 'photos',
};

/** The menu's link to the prepared example, left out once the account holds an insight of its own. */
const EXAMPLE_LINK = '/#example';

const CONTAINER = 'mx-auto w-full max-w-[1200px] px-4 tablet:px-7 desktop:px-6 wide:max-w-[1240px]';

/**
 * The phone's header (no top bar below tablet): the mark, and a menu of the
 * page's sections that opens and closes with a tap, Enter or Space, closes on
 * Escape or a choice, and gives focus back to its button. The capture button
 * stays in sight in the phone's own bar.
 */
function PhoneHeader() {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const button = useRef<HTMLButtonElement>(null);
  const session = useSession();

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <div className={cx(CONTAINER, 'relative flex h-20 items-center justify-between tablet:hidden')}>
      <Link href="/" className="inline-flex min-h-12 items-center">
        <LogoMark title={messages.brand.name} className="h-[42px]" />
      </Link>
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
        className="glass inline-flex size-12 items-center justify-center rounded-full text-fg"
      >
        <MenuIcon />
        <span className="sr-only">{L.nav.menu}</span>
      </button>
      {open ? (
        <nav
          id={menuId}
          aria-label={L.nav.label}
          className="absolute end-4 top-[72px] z-30 w-56 rounded-[18px] border border-line bg-canvas p-2 shadow-[var(--panel-shadow)]"
        >
          <ul className="m-0 flex list-none flex-col p-0">
            {LANDING_LINKS.filter(
              (item) => item.href !== EXAMPLE_LINK || tutorialOffered(session)
            ).map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="flex min-h-12 items-center rounded-[12px] px-3 text-fg hover:bg-surface"
                >
                  {item.label}
                </Link>
              </li>
            ))}
            {session.status === 'signed-in' ? null : (
              <li>
                <Link
                  href="/signin"
                  onClick={() => setOpen(false)}
                  className="flex min-h-12 items-center rounded-[12px] px-3 font-semibold text-primary hover:bg-surface"
                >
                  {messages.nav.signIn}
                </Link>
              </li>
            )}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}

/** Seconds: the title's words rise one after another, then its gold line catches the light. */
const WORD_STEP = 0.09;
const TITLE_START = 0.45;
const GOLD_START = TITLE_START + (L.hero.titleLead.split(' ').length + 1) * WORD_STEP;
const GLINT_AT = Math.round(
  (GOLD_START + L.hero.titleGold.split(' ').length * WORD_STEP + 0.6) * 1000
);

/**
 * A line whose words rise one by one out of a soft blur, in reading order. The
 * words stay the element's own text (no copy for screen readers is needed), and
 * Arabic letters never join across a space, so each word stays whole.
 */
function Words({ text, delay }: { text: string; delay: number }) {
  const words = Array.from(text.matchAll(/\S+/g), (match) => ({ word: match[0], at: match.index }));
  return words.map(({ word, at }, index) => (
    <Fragment key={at}>
      <span className="fx-word" style={{ animationDelay: `${delay + index * WORD_STEP}s` }}>
        {word}
      </span>
      {index < words.length - 1 ? ' ' : null}
    </Fragment>
  ));
}

function Hero() {
  const capture = useCapture();
  return (
    <section aria-labelledby="landing-title" className={CONTAINER}>
      <div className="relative isolate grid items-center gap-6 overflow-hidden rounded-[22px] bg-[linear-gradient(135deg,#082e25_0%,#0f4c3a_100%)] px-[25px] py-[29px] text-[#ffffff] tablet:grid-cols-2 tablet:rounded-[24px] tablet:px-9 tablet:py-[38px] desktop:min-h-[566px] desktop:rounded-[28px] desktop:px-16 desktop:py-[46px]">
        <HeroAtmosphere />
        <div className="relative flex min-w-0 flex-col items-start gap-5">
          <p className="m-0 flex items-center gap-3 text-[0.9375rem] text-[rgb(255_255_255/0.85)]">
            <span
              aria-hidden="true"
              className="fx-thread fx-thread--now h-px w-5 bg-[#c6a15b]"
              style={revealDelay(0, 0, 150)}
            />
            <span className="fx-rise" style={revealDelay(0, 0, 250)}>
              {L.hero.kicker}
            </span>
          </p>
          <h1
            id="landing-title"
            className="m-0 font-bold font-display text-[2.125rem] leading-[1.5] tablet:text-[2.75rem] desktop:text-[3.375rem]"
          >
            <span className="block">
              <Words text={L.hero.titleLead} delay={TITLE_START} />
            </span>
            <span className="fx-glint block text-[#dfbd77]" style={revealDelay(0, 0, GLINT_AT)}>
              <Words text={L.hero.titleGold} delay={GOLD_START} />
            </span>
          </h1>
          <p
            className="fx-rise m-0 max-w-[34rem] text-[1.0625rem] text-[rgb(255_255_255/0.86)] leading-[1.9]"
            style={revealDelay(0, 0, 1150)}
          >
            {L.hero.lead}
          </p>
          <div className="fx-rise flex w-full flex-wrap gap-3" style={revealDelay(0, 0, 1400)}>
            <button
              type="button"
              onClick={capture.open}
              aria-haspopup="dialog"
              className="relative inline-flex min-h-12 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-[14px] bg-[#dfbd77] px-4 font-semibold text-[#202616] text-[1.0625rem] transition-[filter] duration-200 hover:brightness-105 focus-visible:outline-3 focus-visible:outline-[#ffffff] focus-visible:outline-offset-2 tablet:min-h-[52px] tablet:flex-none tablet:px-6"
            >
              {/* The call to capture breathes out a ring of light three times, then rests. */}
              <span
                aria-hidden="true"
                className="fx-halo pointer-events-none absolute inset-0 rounded-[14px] border-2 border-[#dfbd77]"
                style={revealDelay(0, 0, 2300)}
              />
              <CameraIcon width="20" height="20" />
              {messages.nav.captureScene}
            </button>
            <Link
              href="#example"
              className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-[14px] border border-[rgb(255_255_255/0.45)] px-4 font-semibold text-[#ffffff] text-[1.0625rem] transition-colors duration-200 hover:bg-[rgb(255_255_255/0.08)] focus-visible:outline-3 focus-visible:outline-[#ffffff] focus-visible:outline-offset-2 tablet:min-h-[52px] tablet:flex-none tablet:px-6"
            >
              {L.hero.tryExample}
              {/* Onward, where Arabic reads: at the end of the label, pointing left. */}
              <OnwardArrowIcon width="18" height="18" />
            </Link>
          </div>
          <p
            className="fx-rise m-0 flex items-center gap-2 text-[0.875rem] text-[rgb(255_255_255/0.8)]"
            style={revealDelay(0, 0, 1600)}
          >
            <ShieldIcon width="16" height="16" />
            {L.hero.noAccount}
          </p>
        </div>
        <div className="relative">
          <PhonePreview />
        </div>
      </div>
    </section>
  );
}

function SectionHeading({
  id,
  eyebrow,
  title,
  aside,
}: Readonly<{
  id: string;
  eyebrow?: string;
  title: string;
  aside?: string;
}>) {
  const reveal = useReveal<HTMLDivElement>();
  return (
    <div
      {...reveal}
      className="fx-reveal flex flex-col gap-2 tablet:flex-row tablet:items-end tablet:justify-between tablet:gap-8"
    >
      <div className="flex flex-col gap-2">
        {eyebrow === undefined ? null : (
          <p className="m-0 flex items-center gap-2.5 font-semibold text-[0.875rem] text-[var(--landing-gold)]">
            <span
              aria-hidden="true"
              className="fx-thread h-px w-4 bg-current"
              style={revealDelay(0, 0, 300)}
            />
            {eyebrow}
          </p>
        )}
        <h2
          id={id}
          className="m-0 font-bold font-display text-[1.625rem] text-fg leading-[1.5] tablet:text-[1.75rem] desktop:text-[2.125rem]"
        >
          {title}
        </h2>
      </div>
      {aside === undefined ? null : (
        <p className="m-0 max-w-[18rem] text-[0.9375rem] text-fg-soft leading-[1.8]">{aside}</p>
      )}
    </div>
  );
}

const STEP_EMBLEMS: readonly EmblemName[] = ['camera', 'book', 'sprout'];

function Journey() {
  const reveal = useReveal<HTMLOListElement>();
  return (
    <section
      id="how"
      aria-labelledby="landing-how"
      className={cx(CONTAINER, 'flex flex-col gap-8')}
    >
      <SectionHeading
        id="landing-how"
        eyebrow={L.journey.eyebrow}
        title={L.journey.title}
        aside={L.journey.aside}
      />
      <ol {...reveal} className="m-0 grid list-none gap-6 p-0 tablet:grid-cols-3">
        {L.journey.steps.map((step, index) => {
          return (
            <li
              key={step.title}
              className="fx-reveal-item relative flex flex-col gap-3 border-line border-t pt-5"
              style={revealDelay(index, 220)}
            >
              <span
                aria-hidden="true"
                className="fx-thread absolute inset-x-0 -top-px h-px bg-[var(--landing-gold)]"
                style={revealDelay(index, 220, 250)}
              />
              <div className="flex items-center justify-between">
                <EmblemTile name={STEP_EMBLEMS[index] as EmblemName} size="lg">
                  <span
                    className="fx-halo fx-halo--on-reveal pointer-events-none absolute inset-0 rounded-[16px] border border-[var(--landing-gold)]"
                    style={revealDelay(index, 220, 700)}
                  />
                </EmblemTile>
                <span aria-hidden="true" className="text-[1.75rem] text-fg-muted">
                  {String(index + 1).padStart(2, '0')}
                </span>
              </div>
              <h3 className="m-0 font-semibold text-[1.125rem] text-fg">{step.title}</h3>
              <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.8]">{step.text}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function StoryCard({
  story,
  index,
  tutorial,
}: Readonly<{ story: Story; index: number; tutorial: boolean }>) {
  const action = story.action?.kind === 'example' && !tutorial ? null : story.action;
  const actionClass =
    'inline-flex min-h-12 items-center gap-2 self-start font-semibold text-primary underline-offset-4 hover:underline';
  return (
    <article
      aria-labelledby={`story-${story.id}`}
      className="fx-reveal-item flex min-w-0 flex-col overflow-hidden rounded-[22px] border border-line bg-surface tablet:grid tablet:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] desktop:flex"
      style={revealDelay(index, 180)}
    >
      <div className="relative h-[220px] w-full shrink-0 overflow-hidden tablet:h-full tablet:min-h-[220px] desktop:h-[228px]">
        <div className="fx-settle absolute inset-0" style={revealDelay(index, 180)}>
          <Image
            src={story.image.src}
            alt={story.image.alt}
            fill
            sizes="(min-width: 1200px) 400px, (min-width: 768px) 40vw, 100vw"
            className="object-cover"
          />
        </div>
        <span className="absolute end-3 bottom-3 rounded-full bg-[#f6faf7] px-3 py-1 font-semibold text-[#16302a] text-[0.8125rem] shadow">
          {story.tag}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-6">
        <div className="flex flex-col gap-1.5">
          <h3 id={`story-${story.id}`} className="m-0 font-bold text-[1.375rem] text-fg">
            {story.title}
          </h3>
          <p className="m-0 text-[0.9375rem] text-fg-soft">{story.lead}</p>
        </div>
        <ul className="m-0 flex list-none flex-col gap-4 border-line border-t p-0 pt-4">
          {story.benefits.map((item) => (
            <li key={item.title} className="flex items-start gap-3.5">
              <EmblemTile name={BENEFIT_EMBLEMS[item.icon]} />
              <span className="flex min-w-0 flex-col gap-1 pt-0.5">
                <span className="font-semibold text-fg">{item.title}</span>
                <span className="text-[0.875rem] text-fg-soft leading-[1.8]">{item.text}</span>
              </span>
            </li>
          ))}
        </ul>
        {action === null ? null : action.kind === 'link' ? (
          <Link href={action.href} className={cx(actionClass, 'mt-auto')}>
            <Emblem name={BENEFIT_EMBLEMS[action.icon]} width="20" height="20" />
            {action.label}
          </Link>
        ) : (
          <Link href="#example" className={cx(actionClass, 'mt-auto')}>
            <Emblem name={BENEFIT_EMBLEMS[action.icon]} width="20" height="20" />
            {action.label}
          </Link>
        )}
      </div>
    </article>
  );
}

function Stories({
  features,
  tutorial,
}: Readonly<{ features: LandingFeatures; tutorial: boolean }>) {
  const stories = featureStories(features);
  const reveal = useReveal<HTMLDivElement>();
  return (
    <section
      id="features"
      aria-labelledby="landing-features"
      className={cx(CONTAINER, 'flex flex-col gap-8')}
    >
      <SectionHeading
        id="landing-features"
        eyebrow={L.features.eyebrow}
        title={L.features.title}
        aside={L.features.aside}
      />
      <div {...reveal} className="grid gap-6 desktop:grid-cols-3">
        {stories.map((story, index) => (
          <StoryCard key={story.id} story={story} index={index} tutorial={tutorial} />
        ))}
      </div>
    </section>
  );
}

function Example() {
  const reveal = useReveal<HTMLDivElement>();
  return (
    <section
      id="example"
      aria-labelledby="landing-example"
      className="bg-[var(--landing-band)] py-10 tablet:py-14"
    >
      <div className={cx(CONTAINER, 'flex flex-col gap-8')}>
        <div {...reveal} className="fx-reveal flex flex-col gap-2">
          <h2
            id="landing-example"
            className="m-0 font-bold font-display text-[1.625rem] text-fg leading-[1.5] tablet:text-[1.75rem] desktop:text-[2.125rem]"
          >
            {L.example.title}
          </h2>
          <p className="m-0 max-w-[40rem] text-fg-soft leading-[1.8]">{L.example.lead}</p>
        </div>
        <InsightExample />
      </div>
    </section>
  );
}

/**
 * The first screen of an account that holds an insight of its own (decision 64 (6)): the
 * prepared example is no longer offered, so the capture card is the whole first screen.
 */
function OwnCapture() {
  const capture = useCapture();
  return (
    <section
      aria-labelledby="landing-own-title"
      className={cx(CONTAINER, 'flex min-h-[70dvh] flex-col items-center justify-center gap-4')}
    >
      <h1 id="landing-own-title" className="sr-only">
        {messages.brand.name}
      </h1>
      <CaptureCard onCamera={capture.open} onFile={capture.send} className="w-full max-w-[34rem]" />
    </section>
  );
}

const TRUST_EMBLEMS: readonly EmblemName[] = ['book', 'lantern', 'choice'];

function Trust() {
  const reveal = useReveal<HTMLUListElement>();
  return (
    <section aria-labelledby="landing-trust" className={cx(CONTAINER, 'flex flex-col gap-8')}>
      <SectionHeading id="landing-trust" title={L.trust.title} />
      <ul {...reveal} className="m-0 grid list-none gap-6 p-0 desktop:grid-cols-3">
        {L.trust.items.map((item, index) => {
          return (
            <li
              key={item.title}
              className="fx-reveal-item flex flex-col gap-2 rounded-[18px] border border-line bg-surface p-5"
              style={revealDelay(index, 160)}
            >
              <EmblemTile name={TRUST_EMBLEMS[index] as EmblemName} size="lg" className="mb-2" />
              <span className="font-semibold text-[1.0625rem] text-fg">{item.title}</span>
              <span className="text-[0.9375rem] text-fg-soft leading-[1.8]">{item.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Questions() {
  const reveal = useReveal<HTMLDivElement>();
  return (
    <section aria-labelledby="landing-faq" className={cx(CONTAINER, 'flex flex-col gap-6')}>
      <SectionHeading id="landing-faq" title={L.faq.title} />
      <div {...reveal} className="flex flex-col gap-3">
        {L.faq.items.map((item, index) => (
          <details
            key={item.question}
            className="fx-reveal-item group rounded-[18px] border border-line bg-surface"
            style={revealDelay(index, 90)}
          >
            <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-5 font-semibold text-fg [&::-webkit-details-marker]:hidden">
              {item.question}
              <span
                aria-hidden="true"
                className="text-fg-muted transition-transform duration-200 group-open:-rotate-90"
              >
                <OnwardIcon width="18" height="18" />
              </span>
            </summary>
            <p className="m-0 px-5 pb-5 text-[0.9375rem] text-fg-soft leading-[1.9]">
              {item.answer}
            </p>
          </details>
        ))}
      </div>
    </section>
  );
}

function Closing() {
  const capture = useCapture();
  const reveal = useReveal<HTMLDivElement>();
  return (
    <section aria-labelledby="landing-closing" className={CONTAINER}>
      <div
        {...reveal}
        className="fx-reveal relative isolate flex flex-col items-center gap-5 overflow-hidden rounded-[22px] border border-line bg-surface px-6 py-10 text-center tablet:py-12"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-1/2 -z-10 size-[520px] -translate-x-1/2 -translate-y-1/2"
        >
          <KhatamStar className="fx-turn-back size-full text-[var(--landing-gold)] opacity-25" />
        </div>
        <h2
          id="landing-closing"
          className="m-0 font-bold font-display text-[1.625rem] text-fg leading-[1.5] tablet:text-[2rem]"
        >
          {L.closing.title}
        </h2>
        <button
          type="button"
          onClick={capture.open}
          aria-haspopup="dialog"
          className="fill-primary relative inline-flex min-h-[52px] items-center gap-2 rounded-[14px] px-7 font-semibold text-[1.0625rem] hover:brightness-110 focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-2"
        >
          <span
            aria-hidden="true"
            className="fx-halo fx-halo--on-reveal pointer-events-none absolute inset-0 rounded-[14px] border-2 border-[var(--landing-gold)]"
            style={revealDelay(0, 0, 900)}
          />
          <CameraIcon width="20" height="20" />
          {L.closing.cta}
        </button>
      </div>
    </section>
  );
}

/**
 * The landing page (the owners' landing prompt of 5 October 2026): what TABSIRA
 * does and the two ways in, a photo of one's own or the prepared example, with
 * one tap each. The hero's phone is a still picture; no camera runs and no
 * permission is asked until the reader taps the capture button. The features shown
 * are the ones switched on, from the server's flags. An account that holds an insight of its
 * own gets the capture card in place of the hero and no example (decision 64 (6)). `community`
 * is the server-rendered box of public counts, placed after the steps so that on a phone it is
 * never on the first screen beside the capture (decision 62).
 */
export function LandingPage({
  features,
  community = null,
}: Readonly<{
  features: LandingFeatures;
  community?: ReactNode;
}>) {
  const session = useSession();
  const tutorial = tutorialOffered(session);
  // The page is the same for everyone and the session is known only in the browser: until it
  // is, both openings are there and the device's mark (own-insight.ts) hides one before paint.
  const known = session.status === 'signed-in' || session.status === 'guest';
  return (
    <div className="flex flex-col gap-10 pb-10 tablet:gap-14 tablet:pt-6 desktop:gap-[68px]">
      <div className="flex flex-col">
        <PhoneHeader />
        {known ? (
          tutorial ? (
            <Hero />
          ) : (
            <OwnCapture />
          )
        ) : (
          <>
            <div className="only-without-own-insight">
              <Hero />
            </div>
            <div className="only-with-own-insight">
              <OwnCapture />
            </div>
          </>
        )}
      </div>
      <Journey />
      {community}
      <Stories features={features} tutorial={tutorial} />
      {known ? (
        tutorial ? (
          <Example />
        ) : null
      ) : (
        <div className="only-without-own-insight">
          <Example />
        </div>
      )}
      <Trust />
      <Questions />
      <Closing />
    </div>
  );
}
