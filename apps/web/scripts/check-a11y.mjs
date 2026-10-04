// Accessibility, measured in a real browser (docs/SEO.md §7: axe, WCAG 2.2 AA).
// Colour contrast is computed from what is painted, so jsdom cannot answer it;
// this drives a local Chromium through the DevTools protocol, injects axe-core
// (a pinned dev dependency, nothing fetched) and fails on any serious or
// critical violation.
//
//   pnpm --filter @tabsira/web check:a11y [base-url]
//
// Checked, in both themes, at 375 and 1440 px: the scene (/), the cookie
// screen of a first visit, the sign-in page and «ملفي» signed in. The API is
// answered with the samples of scripts/lib/api-mock.mjs.

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { mockApi, recordedConsentId } from './lib/api-mock.mjs';
import { emulate, visit, withPage } from './lib/chrome.mjs';

const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const BLOCKING = new Set(['serious', 'critical']);

const CHECKS = [
  { name: 'scene', path: '/', consent: 'decided', state: 'guest' },
  { name: 'consent screen', path: '/', consent: 'ask', state: 'guest' },
  { name: 'sign-in', path: '/signin', consent: 'decided', state: 'guest' },
  { name: 'ملفي', path: '/me', consent: 'decided', state: 'signed-in' },
];

async function main() {
  const base = process.argv[2] ?? 'https://tabsira.test';
  const siteOrigin = new URL(base).origin;
  const url = new URL(base);
  const apiOrigin = `${url.protocol}//api.${url.host}`;
  const state = { value: 'guest' };
  const consentId = await recordedConsentId();
  let failures = 0;

  await withPage(async (page) => {
    const { send } = page;
    await send('Network.enable');
    await mockApi(page, { apiOrigin, siteOrigin, state });
    for (const check of CHECKS) {
      state.value = check.state;
      for (const theme of ['dark', 'light']) {
        for (const width of [375, 1440]) {
          await send('Network.clearBrowserCookies');
          if (check.consent === 'decided') {
            await send('Network.setCookie', {
              name: 'tabsira_consent',
              value: consentId,
              url: siteOrigin,
              path: '/',
            });
          }
          await emulate(send, { width, height: width < 768 ? 812 : 900, theme });
          await visit(page, new URL(check.path, base).href, 2500);
          await send('Runtime.evaluate', { expression: AXE });
          const { result } = await send('Runtime.evaluate', {
            expression: `axe.run(document, { runOnly: { type: 'tag', values: ${JSON.stringify(TAGS)} } }).then((r) => JSON.stringify(r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target.join(' ')).slice(0, 5) }))))`,
            awaitPromise: true,
            returnByValue: true,
          });
          const violations = JSON.parse(result.value);
          const blocking = violations.filter((violation) => BLOCKING.has(violation.impact));
          failures += blocking.length;
          const label = `${check.name} ${width}px ${theme}`;
          console.log(
            `${blocking.length === 0 ? 'ok  ' : 'FAIL'} ${label}: ${blocking.length} serious or critical, ${violations.length - blocking.length} minor`
          );
          for (const violation of violations) {
            console.log(
              `     ${violation.impact} ${violation.id}: ${violation.help} ${violation.nodes.join(' | ')}`
            );
          }
        }
      }
    }
  });
  if (failures > 0) {
    process.exitCode = 1;
  }
}

await main();
