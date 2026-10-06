import { readFileSync } from 'node:fs';
import path from 'node:path';

export type TokenSet = Record<string, string>;

export const TOKENS_PATH = path.resolve(__dirname, '../theme/tokens.css');

function declarations(block: string): TokenSet {
  const tokens: TokenSet = {};
  for (const match of block.matchAll(/--([a-z0-9-]+)\s*:([^;]+);/g)) {
    tokens[match[1] as string] = (match[2] as string).replace(/\s+/g, ' ').trim();
  }
  return tokens;
}

function blockAfter(css: string, selector: string): string {
  const start = css.indexOf(selector);
  if (start === -1) {
    throw new Error(`selector not found in tokens.css: ${selector}`);
  }
  const open = css.indexOf('{', start);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    if (css[i] === '}') depth -= 1;
    if (depth === 0) return css.slice(open + 1, i);
  }
  throw new Error(`unbalanced braces after ${selector}`);
}

/** The light tokens, the dark tokens, and the copy of the dark ones under prefers-color-scheme. */
export function readTokens(css = readFileSync(TOKENS_PATH, 'utf8')) {
  return {
    light: declarations(blockAfter(css, ':root,\n[data-theme="light"]')),
    darkSystem: declarations(blockAfter(css, ':root:not([data-theme="light"])')),
    dark: declarations(blockAfter(css, '\n[data-theme="dark"]')),
  };
}
