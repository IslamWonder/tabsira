'use client';

import { useSyncExternalStore } from 'react';

/**
 * Reading aids for this device, chosen in the profile page, for everyone,
 * signed in or not: a larger text, a stronger contrast and underlined links.
 * Each one sets an attribute on <html> that globals.css reads, before the
 * first paint (init-script.ts) and on every change. Only a value other than
 * the default is stored, so clearing the device's data brings the defaults
 * back, and a blocked storage still applies the choice for this visit.
 *
 * The device's own «increase contrast» setting is honoured by globals.css
 * whatever is chosen here; this switch adds the same for a device that has
 * no such setting.
 */

export const TEXT_SIZES = ['normal', 'large', 'larger'] as const;
export type TextSize = (typeof TEXT_SIZES)[number];

export interface ReadingAid<T extends string> {
  /** The localStorage key. */
  key: string;
  /** The data attribute on <html>, without its `data-` prefix; absent at the default. */
  attribute: string;
  values: readonly T[];
  fallback: T;
}

export const TEXT_SIZE: ReadingAid<TextSize> = {
  key: 'tabsira.text-size',
  attribute: 'text-size',
  values: TEXT_SIZES,
  fallback: 'normal',
};

export const CONTRAST: ReadingAid<'normal' | 'more'> = {
  key: 'tabsira.contrast',
  attribute: 'contrast',
  values: ['normal', 'more'],
  fallback: 'normal',
};

export const LINKS: ReadingAid<'normal' | 'underline'> = {
  key: 'tabsira.links',
  attribute: 'links',
  values: ['normal', 'underline'],
  fallback: 'normal',
};

/** Every reading aid, for the script that applies them before the first paint. */
export const READING_AIDS = [TEXT_SIZE, CONTRAST, LINKS] as const;

const CHANGE_EVENT = 'tabsira:reading-aid-change';

export function readChoice<T extends string>(choice: ReadingAid<T>): T {
  try {
    const stored = window.localStorage.getItem(choice.key);
    return choice.values.find((value) => value === stored) ?? choice.fallback;
  } catch {
    return choice.fallback;
  }
}

function apply<T extends string>(choice: ReadingAid<T>, value: T): void {
  const root = document.documentElement;
  if (value === choice.fallback) {
    root.removeAttribute(`data-${choice.attribute}`);
  } else {
    root.setAttribute(`data-${choice.attribute}`, value);
  }
}

export function setChoice<T extends string>(choice: ReadingAid<T>, value: T): void {
  try {
    if (value === choice.fallback) {
      window.localStorage.removeItem(choice.key);
    } else {
      window.localStorage.setItem(choice.key, value);
    }
  } catch {
    // Not stored, but still applied for this visit.
  }
  apply(choice, value);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Calls `onChange` after a change made here or in another tab, which is applied here too. */
export function subscribeReadingAids(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    const changed = READING_AIDS.filter((aid) => event.key === null || event.key === aid.key);
    for (const aid of changed) {
      apply(aid, readChoice(aid));
    }
    if (changed.length > 0) {
      onChange();
    }
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

export function useChoice<T extends string>(choice: ReadingAid<T>): T {
  return useSyncExternalStore(
    subscribeReadingAids,
    () => readChoice(choice),
    () => choice.fallback
  );
}
