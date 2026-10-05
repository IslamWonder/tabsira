'use client';

import Image from 'next/image';
import Link from 'next/link';
import { type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { useSession } from '@/account/session';
import { LogoMark } from '@/components/brand/logo';
import { useCapture } from '@/components/capture/capture-provider';
import {
  AtlasIcon,
  CameraIcon,
  CommentIcon,
  CommunityIcon,
  CompassIcon,
  GemIcon,
  MenuIcon,
  OnwardIcon,
  OpenBookIcon,
  PhotosIcon,
  PlayIcon,
  SeedlingIcon,
  ShieldIcon,
  SparkIcon,
  VerifyIcon,
  WorldIcon,
} from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
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

const ICONS: Record<BenefitIcon, (props: { width: string; height: string }) => ReactNode> = {
  lens: CameraIcon,
  chat: CommentIcon,
  verify: VerifyIcon,
  world: WorldIcon,
  atlas: AtlasIcon,
  around: CompassIcon,
  treasure: GemIcon,
  community: CommunityIcon,
  photos: PhotosIcon,
};

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
            {LANDING_LINKS.map((item) => (
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

function Hero() {
  const capture = useCapture();
  return (
    <section aria-labelledby="landing-title" className={CONTAINER}>
      <div className="grid items-center gap-6 overflow-hidden rounded-[22px] bg-[linear-gradient(135deg,#082e25_0%,#0f4c3a_100%)] px-[25px] py-[29px] text-[#ffffff] tablet:grid-cols-2 tablet:rounded-[24px] tablet:px-9 tablet:py-[38px] desktop:min-h-[566px] desktop:rounded-[28px] desktop:px-16 desktop:py-[46px]">
        <div className="flex min-w-0 flex-col items-start gap-5">
          <p className="m-0 flex items-center gap-3 text-[0.9375rem] text-[rgb(255_255_255/0.85)]">
            <span aria-hidden="true" className="h-px w-5 bg-[#c6a15b]" />
            {L.hero.kicker}
          </p>
          <h1
            id="landing-title"
            className="m-0 font-bold font-display text-[2.125rem] leading-[1.5] tablet:text-[2.75rem] desktop:text-[3.375rem]"
          >
            <span className="block">{L.hero.titleLead}</span>
            <span className="block text-[#dfbd77]">{L.hero.titleGold}</span>
          </h1>
          <p className="m-0 max-w-[34rem] text-[1.0625rem] text-[rgb(255_255_255/0.86)] leading-[1.9]">
            {L.hero.lead}
          </p>
          <div className="flex w-full flex-wrap gap-3">
            <button
              type="button"
              onClick={capture.open}
              aria-haspopup="dialog"
              className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-[14px] bg-[#dfbd77] px-4 font-semibold text-[#202616] text-[1.0625rem] transition-[filter] duration-200 hover:brightness-105 focus-visible:outline-3 focus-visible:outline-[#ffffff] focus-visible:outline-offset-2 tablet:min-h-[52px] tablet:flex-none tablet:px-6"
            >
              <CameraIcon width="20" height="20" />
              {messages.nav.captureScene}
            </button>
            <Link
              href="#example"
              className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-[14px] border border-[rgb(255_255_255/0.45)] px-4 font-semibold text-[#ffffff] text-[1.0625rem] transition-colors duration-200 hover:bg-[rgb(255_255_255/0.08)] focus-visible:outline-3 focus-visible:outline-[#ffffff] focus-visible:outline-offset-2 tablet:min-h-[52px] tablet:flex-none tablet:px-6"
            >
              <PlayIcon width="18" height="18" />
              {L.hero.tryExample}
            </Link>
          </div>
          <p className="m-0 flex items-center gap-2 text-[0.875rem] text-[rgb(255_255_255/0.8)]">
            <ShieldIcon width="16" height="16" />
            {L.hero.noAccount}
          </p>
        </div>
        <PhonePreview />
      </div>
    </section>
  );
}

function SectionHeading({
  id,
  eyebrow,
  title,
  aside,
}: {
  id: string;
  eyebrow?: string;
  title: string;
  aside?: string;
}) {
  return (
    <div className="flex flex-col gap-2 tablet:flex-row tablet:items-end tablet:justify-between tablet:gap-8">
      <div className="flex flex-col gap-2">
        {eyebrow === undefined ? null : (
          <p className="m-0 font-semibold text-[0.875rem] text-[var(--landing-gold)]">{eyebrow}</p>
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

const STEP_ICONS = [CameraIcon, OpenBookIcon, SeedlingIcon] as const;

function Journey() {
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
      <ol className="m-0 grid list-none gap-6 p-0 tablet:grid-cols-3">
        {L.journey.steps.map((step, index) => {
          const Icon = STEP_ICONS[index] as (typeof STEP_ICONS)[number];
          return (
            <li key={step.title} className="flex flex-col gap-3 border-line border-t pt-5">
              <div className="flex items-center justify-between">
                <span className="flex size-12 items-center justify-center rounded-[14px] bg-surface text-primary">
                  <Icon width="22" height="22" />
                </span>
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

function StoryCard({ story }: { story: Story }) {
  const { action } = story;
  const ActionIcon = action === null ? null : ICONS[action.icon];
  const actionClass =
    'inline-flex min-h-12 items-center gap-2 self-start font-semibold text-primary underline-offset-4 hover:underline';
  return (
    <article
      aria-labelledby={`story-${story.id}`}
      className="flex min-w-0 flex-col overflow-hidden rounded-[22px] border border-line bg-surface tablet:grid tablet:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] desktop:flex"
    >
      <div className="relative h-[220px] w-full shrink-0 tablet:h-full tablet:min-h-[220px] desktop:h-[228px]">
        <Image
          src={story.image.src}
          alt={story.image.alt}
          fill
          sizes="(min-width: 1200px) 400px, (min-width: 768px) 40vw, 100vw"
          className="object-cover"
        />
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
          {story.benefits.map((item) => {
            const Icon = ICONS[item.icon];
            return (
              <li key={item.title} className="flex flex-col gap-1">
                <span className="flex items-center gap-2 font-semibold text-fg">
                  <span className="text-[var(--landing-gold)]">
                    <Icon width="18" height="18" />
                  </span>
                  {item.title}
                </span>
                <span className="text-[0.875rem] text-fg-soft leading-[1.8]">{item.text}</span>
              </li>
            );
          })}
        </ul>
        {action === null || ActionIcon === null ? null : action.kind === 'link' ? (
          <Link href={action.href} className={cx(actionClass, 'mt-auto')}>
            <ActionIcon width="18" height="18" />
            {action.label}
          </Link>
        ) : (
          <Link href="#example" className={cx(actionClass, 'mt-auto')}>
            <ActionIcon width="18" height="18" />
            {action.label}
          </Link>
        )}
      </div>
    </article>
  );
}

function Stories({ features }: { features: LandingFeatures }) {
  const stories = featureStories(features);
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
      <div className="grid gap-6 desktop:grid-cols-3">
        {stories.map((story) => (
          <StoryCard key={story.id} story={story} />
        ))}
      </div>
    </section>
  );
}

function Example() {
  return (
    <section
      id="example"
      aria-labelledby="landing-example"
      className="bg-[var(--landing-band)] py-10 tablet:py-14"
    >
      <div className={cx(CONTAINER, 'flex flex-col gap-8')}>
        <div className="flex flex-col gap-2">
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

const TRUST_ICONS = [OpenBookIcon, SparkIcon, ShieldIcon] as const;

function Trust() {
  return (
    <section aria-labelledby="landing-trust" className={cx(CONTAINER, 'flex flex-col gap-8')}>
      <SectionHeading id="landing-trust" title={L.trust.title} />
      <ul className="m-0 grid list-none gap-6 p-0 desktop:grid-cols-3">
        {L.trust.items.map((item, index) => {
          const Icon = TRUST_ICONS[index] as (typeof TRUST_ICONS)[number];
          return (
            <li
              key={item.title}
              className="flex flex-col gap-2 rounded-[18px] border border-line bg-surface p-5"
            >
              <span className="flex items-center gap-2 font-semibold text-[1.0625rem] text-fg">
                <span className="text-primary">
                  <Icon width="20" height="20" />
                </span>
                {item.title}
              </span>
              <span className="text-[0.9375rem] text-fg-soft leading-[1.8]">{item.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Questions() {
  return (
    <section aria-labelledby="landing-faq" className={cx(CONTAINER, 'flex flex-col gap-6')}>
      <SectionHeading id="landing-faq" title={L.faq.title} />
      <div className="flex flex-col gap-3">
        {L.faq.items.map((item) => (
          <details
            key={item.question}
            className="group rounded-[18px] border border-line bg-surface"
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
  return (
    <section aria-labelledby="landing-closing" className={CONTAINER}>
      <div className="flex flex-col items-center gap-5 rounded-[22px] border border-line bg-surface px-6 py-10 text-center tablet:py-12">
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
          className="fill-primary inline-flex min-h-[52px] items-center gap-2 rounded-[14px] px-7 font-semibold text-[1.0625rem] hover:brightness-110 focus-visible:outline-3 focus-visible:outline-[var(--focus)] focus-visible:outline-offset-2"
        >
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
 * are the ones switched on, from the server's flags.
 */
export function LandingPage({ features }: { features: LandingFeatures }) {
  return (
    <div className="flex flex-col gap-10 pb-10 tablet:gap-14 tablet:pt-6 desktop:gap-[68px]">
      <div className="flex flex-col">
        <PhoneHeader />
        <Hero />
      </div>
      <Journey />
      <Stories features={features} />
      <Example />
      <Trust />
      <Questions />
      <Closing />
    </div>
  );
}
