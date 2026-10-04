// Screenshots for the design review (DESIGN_DECISION.md «Game feel»: every
// screen is reviewed at 375, 768 and 1440 px in both themes; the images go to
// docs/screenshots/). Drives a local Chromium through the DevTools protocol,
// with no npm dependency: Node's own WebSocket and fetch.
//
//   CHROME_PATH=/path/to/chrome pnpm --filter @tabsira/web screenshots [base-url] [path...]
//
// CHROME_PATH defaults to the headless shell that Playwright keeps in
// ~/.cache/ms-playwright. The base URL defaults to https://tabsira.test (the
// local nginx with mkcert TLS); the paths default to / and /dev/ui (the
// gallery exists under `next dev` only).

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../docs/screenshots');
const WIDTHS = [375, 768, 1440];
const HEIGHTS = { 375: 812, 768: 1024, 1440: 900 };
const THEMES = ['dark', 'light'];
const PORT = 9333;

function findChrome() {
  if (process.env.CHROME_PATH) {
    return process.env.CHROME_PATH;
  }
  const cache = path.join(homedir(), '.cache/ms-playwright');
  const shell = existsSync(cache)
    ? readdirSync(cache).find((name) => name.startsWith('chromium_headless_shell'))
    : undefined;
  if (shell === undefined) {
    throw new Error('Set CHROME_PATH to a Chromium or Chrome binary.');
  }
  const folder = path.join(cache, shell);
  const layouts = [
    ['chrome-headless-shell-linux64', 'chrome-headless-shell'],
    ['chrome-linux', 'headless_shell'],
  ];
  const found = layouts
    .map(([dir, binary]) => path.join(folder, dir, binary))
    .find((candidate) => existsSync(candidate));
  if (found === undefined) {
    throw new Error(`No headless shell inside ${folder}; set CHROME_PATH.`);
  }
  return found;
}

function client(url) {
  const socket = new WebSocket(url);
  let next = 1;
  const pending = new Map();
  const waiters = [];
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    } else if (message.method) {
      for (const waiter of waiters.filter((w) => w.method === message.method)) {
        waiters.splice(waiters.indexOf(waiter), 1);
        waiter.resolve(message.params);
      }
    }
  });
  return {
    ready: new Promise((resolve) => socket.addEventListener('open', resolve, { once: true })),
    send(method, params = {}, sessionId) {
      const id = next++;
      socket.send(JSON.stringify({ id, method, params, sessionId }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    },
    once(method) {
      return new Promise((resolve) => waiters.push({ method, resolve }));
    },
    close: () => socket.close(),
  };
}

async function main() {
  const [base = 'https://tabsira.test', ...paths] = process.argv.slice(2);
  const pages = paths.length > 0 ? paths : ['/', '/dev/ui'];
  mkdirSync(OUT, { recursive: true });

  const chrome = spawn(
    findChrome(),
    [
      `--remote-debugging-port=${PORT}`,
      '--headless',
      '--hide-scrollbars',
      '--ignore-certificate-errors',
      '--disable-gpu',
      'about:blank',
    ],
    { stdio: 'ignore' }
  );
  try {
    let version;
    for (let attempt = 0; attempt < 50 && version === undefined; attempt += 1) {
      await sleep(100);
      version = await fetch(`http://127.0.0.1:${PORT}/json/version`)
        .then((response) => response.json())
        .catch(() => undefined);
    }
    const cdp = client(version.webSocketDebuggerUrl);
    await cdp.ready;
    const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
    const send = (method, params) => cdp.send(method, params, sessionId);
    await send('Page.enable');

    for (const page of pages) {
      for (const theme of THEMES) {
        for (const width of WIDTHS) {
          const height = HEIGHTS[width];
          await send('Emulation.setDeviceMetricsOverride', {
            width,
            height,
            deviceScaleFactor: 1,
            mobile: width < 768,
          });
          await send('Emulation.setEmulatedMedia', {
            features: [{ name: 'prefers-color-scheme', value: theme }],
          });
          const loaded = cdp.once('Page.loadEventFired');
          await send('Page.navigate', { url: new URL(page, base).href });
          await loaded;
          // Let the fonts, the photo and the entrance animations settle.
          await sleep(3500);
          const full = page !== '/';
          const metrics = await send('Page.getLayoutMetrics');
          const contentHeight = Math.min(6000, Math.ceil(metrics.cssContentSize.height));
          const shot = await send('Page.captureScreenshot', {
            format: 'jpeg',
            quality: 82,
            captureBeyondViewport: full,
            clip: { x: 0, y: 0, width, height: full ? contentHeight : height, scale: 1 },
          });
          const name = `${page === '/' ? 'home' : page.replaceAll('/', '-').replace(/^-/, '')}-${width}-${theme}.jpg`;
          writeFileSync(path.join(OUT, name), Buffer.from(shot.data, 'base64'));
          console.log(`docs/screenshots/${name}`);
        }
      }
    }
    cdp.close();
  } finally {
    chrome.kill();
  }
}

await main();
