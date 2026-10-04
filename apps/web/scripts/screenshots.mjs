// Screenshots for the design review (DESIGN_DECISION.md «Game feel»: every
// screen is reviewed at 375, 768 and 1440 px in both themes; the images go to
// docs/screenshots/). Drives a local Chromium through the DevTools protocol
// (scripts/lib/chrome.mjs), with no npm dependency.
//
//   pnpm --filter @tabsira/web screenshots [base-url] [shot...] [--out=dir]
//
// Shots: home (the scene, cookie choice made), consent (the first visit's
// cookie screen), signin, me, world and practice (signed in) and dev-ui (the gallery, `next dev`
// only); by default all but dev-ui. The API is answered with the samples of
// scripts/lib/api-mock.mjs, so every screen is in a known state. The base URL
// defaults to https://tabsira.test (the local nginx with mkcert TLS).

import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { mockApi, recordedConsentId } from './lib/api-mock.mjs';
import { emulate, visit, withPage } from './lib/chrome.mjs';

const DOCS = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../docs/screenshots'
);
const WIDTHS = [375, 768, 1440];
const HEIGHTS = { 375: 812, 768: 1024, 1440: 900 };
const THEMES = ['dark', 'light'];

const SHOTS = {
  home: { path: '/', consent: 'decided', state: 'guest', full: false },
  consent: { path: '/', consent: 'ask', state: 'guest', full: false },
  signin: { path: '/signin', consent: 'decided', state: 'guest', full: true },
  me: { path: '/me', consent: 'decided', state: 'signed-in', full: true },
  world: { path: '/world', consent: 'decided', state: 'signed-in', full: true },
  practice: { path: '/me/practice', consent: 'decided', state: 'signed-in', full: true },
  'dev-ui': { path: '/dev/ui', consent: 'decided', state: 'guest', full: true },
  // The first paint without JavaScript: the consent screen must already be there.
  'consent-nojs': { path: '/', consent: 'ask', state: 'guest', full: false, noScript: true },
};

function apiOriginFor(base) {
  const url = new URL(base);
  return `${url.protocol}//api.${url.host}`;
}

async function main() {
  const args = process.argv.slice(2);
  const out = args.find((arg) => arg.startsWith('--out='))?.slice('--out='.length) ?? DOCS;
  const rest = args.filter((arg) => !arg.startsWith('--'));
  const base = rest[0]?.startsWith('http') ? rest.shift() : 'https://tabsira.test';
  const names = rest.length > 0 ? rest : ['home', 'consent', 'signin', 'me'];
  mkdirSync(out, { recursive: true });
  const siteOrigin = new URL(base).origin;
  const state = { value: 'guest' };
  const consentId = await recordedConsentId();

  await withPage(async (page) => {
    const { send } = page;
    await send('Network.enable');
    await mockApi(page, { apiOrigin: apiOriginFor(base), siteOrigin, state });
    for (const name of names) {
      const shot = SHOTS[name];
      if (shot === undefined) {
        throw new Error(`Unknown shot "${name}": ${Object.keys(SHOTS).join(', ')}`);
      }
      state.value = shot.state;
      for (const theme of THEMES) {
        for (const width of WIDTHS) {
          const height = HEIGHTS[width];
          await send('Network.clearBrowserCookies');
          if (shot.consent === 'decided') {
            await send('Network.setCookie', {
              name: 'tabsira_consent',
              value: consentId,
              url: siteOrigin,
              path: '/',
            });
          }
          await emulate(send, { width, height, theme });
          await send('Emulation.setScriptExecutionDisabled', { value: shot.noScript === true });
          await visit(page, new URL(shot.path, base).href);
          let shotHeight = height;
          if (shot.full) {
            // A window as tall as the page, so the fixed backdrop covers all of it;
            // full-height layouts keep the height of the real window.
            await send('Runtime.evaluate', {
              expression: `document.documentElement.style.setProperty('--app-height', '${height}px')`,
            });
            const metrics = await send('Page.getLayoutMetrics');
            shotHeight = Math.min(6000, Math.ceil(metrics.cssContentSize.height));
            await emulate(send, { width, height: shotHeight, theme });
            await sleep(600);
          }
          const capture = await send('Page.captureScreenshot', {
            format: 'jpeg',
            quality: 82,
            clip: { x: 0, y: 0, width, height: shotHeight, scale: 1 },
          });
          const file = `${name}-${width}-${theme}.jpg`;
          writeFileSync(path.join(out, file), Buffer.from(capture.data, 'base64'));
          console.log(path.join(out, file));
        }
      }
    }
  });
}

await main();
