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
    // The colours change only with the theme, so they are read here and again
    // on a theme change — never once per frame.
    let palette = tokens();

    const draw = () => {
      context.clearRect(0, 0, width, height);
      context.fillStyle = palette.color;
      context.shadowColor = palette.color;
      for (const mote of motes) {
        context.globalAlpha = palette.opacity * moteAlpha(mote, time);
        context.shadowBlur = mote.radius * 4;
        context.beginPath();
        context.arc(mote.x + moteOffset(mote, time), mote.y, mote.radius, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
    };

    const reread = () => {
      palette = tokens();
      draw();
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
    const observer = new MutationObserver(reread);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    const scheme = window.matchMedia('(prefers-color-scheme: dark)');
    scheme.addEventListener('change', reread);
    const unsubscribe = subscribeAmbientMotion(sync);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', sync);
      observer.disconnect();
      scheme.removeEventListener('change', reread);
      unsubscribe();
    };
  }, []);

  // Inside the aria-hidden backdrop; an empty canvas exposes nothing anyway.
  return <canvas ref={ref} className="absolute inset-0 h-full w-full" />;
}
