import { describe, expect, it } from 'vitest';
import { publicInsightOut } from '@/test/share';
import { cardKey, createPngCache } from './cache';

const png = (name: string) => Buffer.from(name);

describe('the memory of cards just drawn', () => {
  it('keys a card by the content and the host', () => {
    const insight = publicInsightOut();
    expect(cardKey(insight, 'tabsira.me')).toBe(cardKey(publicInsightOut(), 'tabsira.me'));
    expect(cardKey(insight, 'tabsira.me')).not.toBe(cardKey(insight, 'tabsira.test'));
    expect(cardKey(insight, 'tabsira.me')).not.toBe(
      cardKey(publicInsightOut({ title: 'عنوان آخر' }), 'tabsira.me')
    );
  });

  it('forgets the least recently used card first', () => {
    const cache = createPngCache(2);
    cache.set('a', png('a'));
    cache.set('b', png('b'));
    expect(cache.get('a')?.toString()).toBe('a');
    cache.set('c', png('c'));
    expect(cache.get('b')).toBeUndefined();
    expect(cache.get('a')?.toString()).toBe('a');
    expect(cache.get('c')?.toString()).toBe('c');
    cache.set('a', png('a2'));
    expect(cache.get('a')?.toString()).toBe('a2');
  });
});
