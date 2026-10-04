// A tiny API for the web server itself, for CI: the same sample answers as
// api-mock.mjs, over HTTP on loopback, so check:a11y runs with no database and
// no real API. The web server asks it about the consent cookie before it
// renders, and check-a11y.mjs records its consent here. Sample data only.
//
//   node scripts/lib/api-stub.mjs [port]      (default 8000, 127.0.0.1 only)

import { createServer } from 'node:http';
import { answer } from './api-mock.mjs';

const port = Number(process.argv[2] ?? 8000);

createServer((request, response) => {
  const pathname = new URL(request.url ?? '/', 'http://127.0.0.1').pathname;
  const { status, body } = answer(request.method ?? 'GET', pathname, 'guest');
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(body));
}).listen(port, '127.0.0.1', () => {
  console.log(`api stub on http://127.0.0.1:${port}`);
});
