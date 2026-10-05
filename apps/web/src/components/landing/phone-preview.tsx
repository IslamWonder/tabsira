import Image from 'next/image';
import type { CSSProperties } from 'react';
import { SparkIcon } from '@/components/icons';
import { RAIN_PHOTO } from '@/components/scene/rain-scene';
import { Emblem } from '@/components/ui/emblem';
import { messages } from '@/messages';

const P = messages.landing.phone;
const DROP = messages.scene.example.insights[0] as { title: string; glimpse: string };

/** Milliseconds after the first paint: the phone lands, the lens looks, then the insight shows. */
const POINT_AT = 3100;

const at = (ms: number) => ({ '--fx-delay': `${ms}ms` }) as CSSProperties;

/** A bead of light riding a ring. */
function Bead() {
  return (
    <span className="absolute top-0 left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#dfbd77] shadow-[0_0_10px_3px_rgb(223_189_119/0.6)]" />
  );
}

/**
 * The hero's phone: a still picture of the prepared rain scene and one insight,
 * drawn with markup over the scene's photo. It is a picture and says so (one
 * description for assistive technology, everything inside hidden): no camera
 * runs, nothing is fetched, and no verse is drawn in it; the example further
 * down shows the texts themselves, from the store. On first paint it plays a
 * short scene once: the phone lands, a light scans its screen, the insight
 * appears and the two cards drift a little before they rest.
 */
export function PhonePreview() {
  return (
    <figure
      role="img"
      aria-label={P.alt}
      className="relative m-0 mx-auto h-[325px] w-full max-w-[420px] tablet:h-[474px]"
    >
      <div aria-hidden="true" className="absolute inset-0">
        {/* Two quiet rings open around the phone, a bead of light travelling on each. */}
        <span
          className="fx-ring-in absolute top-1/2 left-1/2 size-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[rgb(255_255_255/0.08)] tablet:size-[470px]"
          style={at(150)}
        />
        <span
          className="fx-ring-in absolute top-1/2 left-1/2 size-[220px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[rgb(255_255_255/0.1)] tablet:size-[340px]"
          style={at(300)}
        />
        <span className="fx-turn absolute top-1/2 left-1/2 size-[300px] -translate-x-1/2 -translate-y-1/2 tablet:size-[470px]">
          <Bead />
        </span>
        <span className="fx-turn-back absolute top-1/2 left-1/2 size-[220px] -translate-x-1/2 -translate-y-1/2 tablet:size-[340px]">
          <Bead />
        </span>

        <div
          className="fx-phone-in absolute top-1/2 left-1/2 h-[304px] w-[152px] -translate-x-1/2 -translate-y-1/2 -rotate-[8deg] rounded-[28px] border-[5px] border-[#1d2b26] bg-[#0b1210] shadow-[0_30px_60px_rgb(0_0_0/0.4)] tablet:h-[468px] tablet:w-[234px] tablet:rounded-[38px] tablet:border-[7px]"
          style={at(250)}
        >
          <div className="relative size-full overflow-hidden rounded-[22px] tablet:rounded-[30px]">
            <Image
              src={RAIN_PHOTO.src}
              alt=""
              fill
              sizes="(min-width: 768px) 234px, 152px"
              className="object-cover"
              priority
            />
            <div className="absolute inset-0 bg-[linear-gradient(180deg,rgb(0_0_0/0.35),transparent_35%,transparent_55%,rgb(0_0_0/0.45))]" />
            {/* The lens looks: a band of light passes over the scene twice, then the insight appears. */}
            <span className="fx-sweep__band fx-sweep-twice" style={at(1500)} />
            <div className="absolute inset-x-0 top-0 flex items-center justify-between px-3 pt-2 text-[7px] text-[#ffffff] tablet:px-4 tablet:pt-3 tablet:text-[10px]">
              <span className="font-semibold">{P.time}</span>
              <span className="mx-auto h-3 w-12 rounded-full bg-[#000000] tablet:h-4 tablet:w-16" />
            </div>
            <div className="absolute inset-x-0 top-6 flex flex-col items-end gap-1.5 px-3 text-[#ffffff] tablet:top-9 tablet:gap-2 tablet:px-4">
              <span className="font-semibold text-[8px] tablet:text-[12px]">{P.lens}</span>
              {/* The picture is the prepared example, and says so where it shows. */}
              <span className="rounded-full border border-[rgb(255_255_255/0.4)] bg-[rgb(0_0_0/0.25)] px-2 py-0.5 text-[7px] tablet:text-[10px]">
                {messages.scene.prepared}
              </span>
            </div>
            <div
              className="fx-pop-in absolute top-[44%] right-[18%] flex items-center gap-1"
              style={at(POINT_AT)}
            >
              <span className="rounded-full bg-[#f6faf7] px-1.5 py-0.5 font-semibold text-[#16302a] text-[7px] shadow tablet:px-2 tablet:text-[10px]">
                {DROP.title}
              </span>
              <span className="relative flex size-4 items-center justify-center rounded-full border border-[#c6a15b] bg-[#0f4c3a] text-[#dfbd77] tablet:size-6">
                <span
                  className="fx-halo absolute -inset-1 rounded-full border border-[#dfbd77]"
                  style={at(POINT_AT + 300)}
                />
                <SparkIcon width="10" height="10" />
              </span>
            </div>
            <div
              className="fx-rise absolute inset-x-2 bottom-3 flex flex-col gap-1 rounded-[14px] bg-[rgb(246_250_247/0.96)] p-2 text-[#16302a] shadow-lg tablet:inset-x-3 tablet:bottom-5 tablet:gap-1.5 tablet:rounded-[18px] tablet:p-3"
              style={at(POINT_AT + 450)}
            >
              <span className="flex items-center gap-1 text-[#4a635c] text-[6px] tablet:text-[9px]">
                <Emblem name="book" width="9" height="9" />
                {P.insight}
              </span>
              <span className="font-bold text-[9px] tablet:text-[14px]">{DROP.title}</span>
              <span className="text-[#4a635c] text-[7px] leading-[1.6] tablet:text-[10px]">
                {DROP.glimpse}
              </span>
              <span className="mt-0.5 border-[#dce7e1] border-t pt-1 text-[#0f4c3a] text-[6px] tablet:text-[9px]">
                {P.discover}
              </span>
            </div>
          </div>
        </div>

        <div
          style={at(POINT_AT + 1000)}
          className="fx-float absolute top-[14%] right-[2%] flex w-[150px] items-center gap-2 rounded-[14px] bg-[#f6faf7] p-2 text-[#16302a] shadow-[0_12px_28px_rgb(0_0_0/0.25)] tablet:top-[20%] tablet:right-auto tablet:left-[54%] tablet:w-[196px] tablet:p-3"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-[10px] bg-[#faf3e2] text-[#8d6e2c] tablet:size-9">
            <Emblem name="book" width="18" height="18" />
          </span>
          <span className="flex flex-col">
            <span className="font-semibold text-[10px] tablet:text-[12px]">{P.fromScene}</span>
            <span className="text-[#4a635c] text-[8px] tablet:text-[10px]">{P.fromSceneHint}</span>
          </span>
        </div>
        <div
          style={at(POINT_AT + 1300)}
          className="fx-float absolute bottom-[10%] left-[2%] flex items-center gap-2 rounded-[12px] bg-[#f6faf7] px-2.5 py-1.5 text-[#16302a] shadow-[0_12px_28px_rgb(0_0_0/0.25)] tablet:bottom-[14%] tablet:px-3 tablet:py-2"
        >
          <Emblem name="sprout" width="18" height="18" className="text-[#0f4c3a]" />
          <span className="font-semibold text-[10px] tablet:text-[12px]">{P.everyLook}</span>
        </div>
      </div>
    </figure>
  );
}
