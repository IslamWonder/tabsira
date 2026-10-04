'use client';

import { useEffect, useRef } from 'react';
import { motionAllowed, subscribeAmbientMotion } from '@/preferences/motion';
import { createMote, type Mote, moteAlpha, moteCount, moteOffset, stepMote } from './motes';

function tokens() {
  const style = getComputedStyle(document.documentElement);
  return {
    color: style.getPropertyValue('--mote').trim() || '#e6c77f',
    opacity: Number.parseFloat(style.getPropertyValue('--mote-opacity')) || 0.6,
  };
}

/**
 * Slow light motes drifting up behind the content: dust in the light of the
 * scene, never following the pointer. The loop runs only while the page is
 * visible and decorative motion is allowed (device setting and the profile page);
 * otherwise one still frame is drawn. Cheap: a few dozen dots, pixel ratio
 * capped at 2.
 */
export function LightMotes() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current as HTMLCanvasElement;
    const context = canvas.getContext('2d');
    if (context === null) {
      return;
    }
    let motes: Mote[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;
    let last = 0;
    let time = 0;

    const draw = () => {
      const { color, opacity } = tokens();
      context.clearRect(0, 0, width, height);
      context.fillStyle = color;
      context.shadowColor = color;
      for (const mote of motes) {
        context.globalAlpha = opacity * moteAlpha(mote, time);
        context.shadowBlur = mote.radius * 4;
        context.beginPath();
        context.arc(mote.x + moteOffset(mote, time), mote.y, mote.radius, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
    };

    const tick = (now: number) => {
      const dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
      last = now;
      time += dt;
      motes = motes.map((mote) => stepMote(mote, dt, width, height, Math.random));
      draw();
      frame = requestAnimationFrame(tick);
    };

    const sync = () => {
      cancelAnimationFrame(frame);
      if (motionAllowed() && document.visibilityState === 'visible') {
        last = performance.now();
        frame = requestAnimationFrame(tick);
      } else {
        draw();
      }
    };

    const resize = () => {
      const ratio = Math.min(2, window.devicePixelRatio || 1);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      motes = Array.from({ length: moteCount(width, height) }, () =>
        createMote(width, height, Math.random, false)
      );
      sync();
    };

    resize();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', sync);
    const unsubscribe = subscribeAmbientMotion(sync);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', sync);
      unsubscribe();
    };
  }, []);

  // Inside the aria-hidden backdrop; an empty canvas exposes nothing anyway.
  return <canvas ref={ref} className="absolute inset-0 h-full w-full" />;
}
