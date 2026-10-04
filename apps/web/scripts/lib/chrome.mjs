// A local Chromium driven through the DevTools protocol, with no npm
// dependency: Node's own WebSocket and fetch. Shared by screenshots.mjs and
// check-a11y.mjs. CHROME_PATH wins; otherwise the headless shell that
// Playwright keeps in ~/.cache/ms-playwright is used.

import { spawn } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = Number(process.env.CHROME_DEBUG_PORT ?? 9333);

function findChrome() {
  if (process.env.CHROME_PATH) {
    return process.env.CHROME_PATH;
  }
  const onPath = ['chromium', 'chromium-browser', 'google-chrome-stable', 'google-chrome']
    .flatMap((name) =>
      (process.env.PATH ?? '').split(path.delimiter).map((dir) => path.join(dir, name))
    )
    .find((candidate) => existsSync(candidate));
  if (onPath !== undefined) {
    return onPath;
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
  const handlers = new Map();
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
      handlers.get(message.method)?.(message.params, message.sessionId);
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
    on(method, handler) {
      handlers.set(method, handler);
    },
    close: () => socket.close(),
  };
}

/**
 * Starts the browser and opens one page; `run` receives `{ cdp, send }` where
 * `send` talks to that page. The browser is stopped whatever happens.
 */
export async function withPage(run) {
  const chrome = spawn(
    findChrome(),
    [
      `--remote-debugging-port=${PORT}`,
      '--headless',
      '--hide-scrollbars',
      '--ignore-certificate-errors',
      '--disable-gpu',
      ...(process.env.CHROME_NO_SANDBOX === '1' ? ['--no-sandbox'] : []),
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
    try {
      return await run({ cdp, send });
    } finally {
      cdp.close();
    }
  } finally {
    chrome.kill();
  }
}

/** Navigates and waits for the load event, then `settle` ms for fonts, images and entrances. */
export async function visit({ cdp, send }, url, settle = 3500) {
  const loaded = cdp.once('Page.loadEventFired');
  await send('Page.navigate', { url });
  await loaded;
  await sleep(settle);
}

export async function emulate(send, { width, height, theme }) {
  await send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 768,
  });
  await send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-color-scheme', value: theme }],
  });
}
