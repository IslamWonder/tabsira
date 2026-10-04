import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ar } from '@/messages/ar';

const SRC = path.resolve(__dirname, '..');

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) {
      return sourceFiles(full);
    }
    return /\.(ts|tsx|css)$/.test(name) ? [full] : [];
  });
}

const relative = (file: string) => path.relative(SRC, file);
const isTest = (file: string) => /\.test\.tsx?$/.test(file) || relative(file).startsWith('test/');

describe('source guards', () => {
  it('keeps user-visible Arabic in src/messages only (AGENTS.md)', () => {
    const offenders = sourceFiles(SRC)
      .filter((file) => !isTest(file) && !relative(file).startsWith('messages/'))
      .filter((file) =>
        /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]/.test(readFileSync(file, 'utf8'))
      )
      .map(relative);
    expect(offenders).toEqual([]);
  });

  it('contains no Quran text typed by hand, tests included', () => {
    // Uthmani-only marks: small high signs, the superscript alef, alef wasla.
    // Interface copy never uses them; a pasted verse always does.
    const uthmani = /[\u0670\u0671\u06D6-\u06ED\u08F0-\u08FF]/;
    const offenders = sourceFiles(SRC)
      .filter((file) => uthmani.test(readFileSync(file, 'utf8')))
      .map(relative);
    expect(offenders).toEqual([]);
  });
});

describe('messages', () => {
  it('keeps the page title and description short enough for search results (master prompt §25)', () => {
    expect(ar.meta.title.length).toBeLessThanOrEqual(65);
    expect(ar.meta.description.length).toBeLessThanOrEqual(165);
  });

  it('has no empty string', () => {
    const empty: string[] = [];
    const walk = (value: unknown, at: string) => {
      if (typeof value === 'string' && value.trim() === '') {
        empty.push(at);
      } else if (value !== null && typeof value === 'object') {
        for (const [key, child] of Object.entries(value)) {
          walk(child, `${at}.${key}`);
        }
      }
    };
    walk(ar, 'ar');
    expect(empty).toEqual([]);
  });

  it('joins a glimpse and a position with an Arabic comma', () => {
    expect(ar.scene.glimpseAndPosition('أ', 'ب')).toBe('أ، ب');
  });
});
