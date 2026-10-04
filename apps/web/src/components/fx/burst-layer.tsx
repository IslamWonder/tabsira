'use client';

import { useEffect, useRef } from 'react';
import { motionAllowed } from '@/preferences/motion';
import {
  BURST_EVENT,
  type BurstRequest,
  type Particle,
  particleAlpha,
  spawnBurst,
  stepParticles,
} from './burst';

const PALETTE_TOKENS = ['--glow-gold', '--glow-emerald', '--point-gold-core'] as const;
const FALLBACK = ['#e6c77f', '#3fd69a', '#fff4d6'] as const;

function palette(): string[] {
  const style = getComputedStyle(document.documentElement);
  return PALETTE_TOKENS.map(
    (token, index) => style.getPropertyValue(token).trim() || (FALLBACK[index] as string)
  );
}

function star(context: CanvasRenderingContext2D, radius: number) {
  context.beginPath();
  for (let i = 0; i < 16; i += 1) {
    const r = i % 2 === 0 ? radius : radius * 0.5;
    const angle = (i * Math.PI) / 8;
    context.lineTo(Math.cos(angle) * r, Math.sin(angle) * r);
  }
  context.closePath();
}

/**
 * The one canvas that draws bursts, fixed over the page and transparent to
 * the pointer. It draws only while particles live, and not at all when
 * decorative motion is off.
 */
export function BurstLayer() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current as HTMLCanvasElement;
    const context = canvas.getContext('2d');
    if (context === null) {
      return;
    }
    let particles: Particle[] = [];
    let frame = 0;
    let last = 0;

    const resize = () => {
      const ratio = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(window.innerWidth * ratio);
      canvas.height = Math.round(window.innerHeight * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = () => {
      const colours = palette();
      context.clearRect(0, 0, window.innerWidth, window.innerHeight);
      for (const p of particles) {
        context.save();
        context.globalAlpha = particleAlpha(p);
        context.translate(p.x, p.y);
        context.rotate(p.rotation);
        context.fillStyle = colours[p.tone] as string;
        if (p.star) {
          star(context, p.size * 1.8);
        } else {
          context.beginPath();
          context.arc(0, 0, p.size, 0, Math.PI * 2);
        }
        context.fill();
        context.restore();
      }
    };

    const tick = (now: number) => {
      particles = stepParticles(particles, Math.min(0.05, Math.max(0, (now - last) / 1000)));
      last = now;
      draw();
      frame = particles.length > 0 ? requestAnimationFrame(tick) : 0;
    };

    const onBurst = (event: Event) => {
      if (!motionAllowed()) {
        return;
      }
      particles = [
        ...particles,
        ...spawnBurst((event as CustomEvent<BurstRequest>).detail, Math.random),
      ];
      if (frame === 0) {
        last = performance.now();
        frame = requestAnimationFrame(tick);
      }
    };

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener(BURST_EVENT, onBurst);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      window.removeEventListener(BURST_EVENT, onBurst);
    };
  }, []);

  return (
    // An empty canvas has nothing to expose to assistive technology.
    <canvas ref={ref} className="pointer-events-none fixed inset-0 z-[70] h-full w-full" />
  );
}
