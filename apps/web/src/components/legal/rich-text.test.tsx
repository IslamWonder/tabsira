import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { findTokens, RichText } from './rich-text';

// The pattern the tokenizer replaced, kept as the reference it must agree with.
const REFERENCE =
  /(https?:\/\/[^\s،)]*[^\s،).,])|([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|([A-Za-z][A-Za-z0-9]*(?: [A-Za-z][A-Za-z0-9]*)*)/g;

function reference(text: string) {
  return [...text.matchAll(REFERENCE)].map((match) => {
    const [token, url, address] = match;
    let kind = 'email';
    if (url !== undefined) {
      kind = 'url';
    } else if (address === undefined) {
      kind = 'latin';
    }
    return { kind, index: match.index, text: token };
  });
}

const PIECES = [
  'http://',
  'https://',
  'a',
  'B',
  '1',
  '.',
  ',',
  '@',
  '-',
  '_',
  ' ',
  ')',
  'ب',
  '،',
  'co',
  'x.y',
];

/** A small deterministic generator, so a failure repeats. */
function* samples(count: number): Generator<string> {
  let seed = 12_345;
  const next = (limit: number) => {
    seed = (Math.imul(seed, 1_664_525) + 1_013_904_223) >>> 0;
    return Math.floor(seed / 65_536) % limit;
  };
  for (let i = 0; i < count; i += 1) {
    let text = '';
    for (let n = next(9); n > 0; n -= 1) {
      text += PIECES[next(PIECES.length)];
    }
    yield text;
  }
}

describe('findTokens', () => {
  it('finds addresses, e-mail addresses and Latin names as the single pattern did', () => {
    const fixed = [
      '',
      'ب',
      'زر https://tabsira.me/terms. ثم',
      'راسلنا على support@tabsira.me، شكرًا',
      'رابط (http://a.com) وبعده، TABSIRA Web 2 ثم',
      'foo bar-baz@x.com',
      'http://.,.,',
      'a@b.c',
      'a@b.cd',
      'a.b@c.d.ef',
      'a@@b.cd x@y.zz@w.vv',
      'https://x.y/z,.',
    ];
    const differing = [...fixed, ...samples(60_000)].filter(
      (text) => JSON.stringify(findTokens(text)) !== JSON.stringify(reference(text))
    );
    expect(differing).toEqual([]);
    const kinds = new Set(
      [...samples(60_000)].flatMap((text) => findTokens(text).map((t) => t.kind))
    );
    expect([...kinds].sort()).toEqual(['email', 'latin', 'url']);
  });

  it('answers at once for long adversarial runs', () => {
    const started = performance.now();
    findTokens('a.'.repeat(30_000));
    findTokens(`a@${'a.'.repeat(30_000)}`);
    findTokens(`${'a@'.repeat(30_000)}b`);
    findTokens(`http://${'.,'.repeat(30_000)}`);
    findTokens('http://'.repeat(10_000));
    expect(performance.now() - started).toBeLessThan(1500);
  });
});

describe('RichText', () => {
  it('links an address, links an e-mail address and isolates a Latin name', () => {
    const { container } = render(
      <p>
        <RichText text="زر https://tabsira.me/a. أو راسل me@tabsira.me عن TABSIRA Web" />
      </p>
    );
    const links = container.querySelectorAll('a');
    expect(links[0]?.getAttribute('href')).toBe('https://tabsira.me/a');
    expect(links[1]?.getAttribute('href')).toBe('mailto:me@tabsira.me');
    expect(container.querySelector('bdi')?.textContent).toBe('TABSIRA Web');
    expect(container.textContent).toBe(
      'زر https://tabsira.me/a. أو راسل me@tabsira.me عن TABSIRA Web'
    );
  });
});
