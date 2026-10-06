import { Fragment, type ReactNode } from 'react';

type TokenKind = 'url' | 'email' | 'latin';

export interface Token {
  kind: TokenKind;
  index: number;
  text: string;
}

// A web address ends before a space, an Arabic comma or a closing bracket, and
// leaves out a final full stop or comma, which belong to the sentence.
const URL_PREFIX = /https?:\/\//y;
const URL_STOP = /[\s\u060C)]/;
// A run of Latin words (a product name).
const LATIN = /[A-Za-z][A-Za-z0-9]*(?: [A-Za-z][A-Za-z0-9]*)*/y;
const LOCAL_CHAR = /[A-Za-z0-9._%+-]/;
const DOMAIN_CHAR = /[A-Za-z0-9.-]/;
const LETTER = /[A-Za-z]/;

function urlEnd(text: string, at: number): number {
  URL_PREFIX.lastIndex = at;
  if (!URL_PREFIX.test(text)) {
    return -1;
  }
  const start = URL_PREFIX.lastIndex;
  const stop = text.slice(start).search(URL_STOP);
  let end = stop === -1 ? text.length : start + stop;
  while (end > start && '.,'.includes(text.charAt(end - 1))) {
    end -= 1;
  }
  return end > start ? end : -1;
}

/** Where a character class stops, scanning from `from`. */
function runEnd(text: string, from: number, member: RegExp): number {
  let end = from;
  while (end < text.length && member.test(text.charAt(end))) {
    end += 1;
  }
  return end;
}

/** The end of a domain after an `@` (a dot then two letters or more), or -1. */
function domainEnd(text: string, from: number): number {
  const stop = runEnd(text, from, DOMAIN_CHAR);
  let letters = 0;
  for (let dot = stop - 1; dot > from; dot -= 1) {
    letters = LETTER.test(text.charAt(dot + 1)) ? letters + 1 : 0;
    if (text.charAt(dot) === '.' && letters >= 2) {
      return dot + 1 + letters;
    }
  }
  return -1;
}

interface Scan {
  /** The end of the run of local-part characters last measured: its attempts meet the same `@`. */
  localStop: number;
  /** The domain after the `@` last met, with the end of its match or -1. */
  domain: { at: number; end: number };
}

function emailEnd(text: string, at: number, scan: Scan): number {
  if (!LOCAL_CHAR.test(text.charAt(at))) {
    return -1;
  }
  if (scan.localStop <= at) {
    scan.localStop = runEnd(text, at, LOCAL_CHAR);
  }
  if (text.charAt(scan.localStop) !== '@') {
    return -1;
  }
  if (scan.domain.at !== scan.localStop) {
    scan.domain = { at: scan.localStop, end: domainEnd(text, scan.localStop + 1) };
  }
  return scan.domain.end;
}

function tokenAt(text: string, at: number, scan: Scan): Token | null {
  const url = urlEnd(text, at);
  if (url !== -1) {
    return { kind: 'url', index: at, text: text.slice(at, url) };
  }
  const email = emailEnd(text, at, scan);
  if (email !== -1) {
    return { kind: 'email', index: at, text: text.slice(at, email) };
  }
  LATIN.lastIndex = at;
  const latin = LATIN.exec(text);
  return latin === null ? null : { kind: 'latin', index: at, text: latin[0] };
}

/**
 * Finds the addresses, e-mail addresses and Latin names of a text, leftmost first, in that
 * order of preference at one position. Written by hand: one pattern for the three backtracked
 * in quadratic time on a long run of dots.
 */
export function findTokens(text: string): Token[] {
  const tokens: Token[] = [];
  const scan: Scan = { localStop: -1, domain: { at: -1, end: -1 } };
  let at = 0;
  while (at < text.length) {
    const token = tokenAt(text, at, scan);
    if (token === null) {
      at += 1;
    } else {
      tokens.push(token);
      at += token.text.length;
    }
  }
  return tokens;
}

function renderToken({ kind, index, text }: Token): ReactNode {
  if (kind === 'url') {
    return (
      <a key={`u${index}`} href={text} dir="ltr" className="font-medium text-link underline">
        {text}
      </a>
    );
  }
  if (kind === 'latin') {
    return <bdi key={`b${index}`}>{text}</bdi>;
  }
  return (
    <a
      key={`a${index}`}
      href={`mailto:${text}`}
      dir="ltr"
      className="font-medium text-link underline"
    >
      {text}
    </a>
  );
}

/**
 * Plain text with three touches the Arabic page needs: a web address becomes a
 * link and an e-mail address a mailto link, both set left to right, and a Latin
 * name is isolated with <bdi> so it cannot reorder the Arabic around it
 * (docs/SEO.md §4).
 */
export function RichText({ text }: Readonly<{ text: string }>) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const token of findTokens(text)) {
    if (token.index > last) {
      parts.push(<Fragment key={`t${last}`}>{text.slice(last, token.index)}</Fragment>);
    }
    parts.push(renderToken(token));
    last = token.index + token.text.length;
  }
  if (last < text.length) {
    parts.push(<Fragment key={`t${last}`}>{text.slice(last)}</Fragment>);
  }
  return <>{parts}</>;
}
