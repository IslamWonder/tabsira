/**
 * A server-sent events reader on `fetch`, so a request can carry the session
 * cookie, `Last-Event-ID` and an abort signal, and a test can feed it a stream.
 * The API sends `id`, `event` and `data` fields with `\r\n` line ends
 * (sse-starlette); comments (`:`) are heartbeats and are skipped.
 */

export interface SseMessage {
  id: string | null;
  event: string;
  data: string;
}

function parseBlock(block: string): SseMessage | null {
  let id: string | null = null;
  let event = 'message';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) {
      continue;
    }
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    const raw = colon < 0 ? '' : line.slice(colon + 1);
    const value = raw.startsWith(' ') ? raw.slice(1) : raw;
    if (field === 'data') {
      data.push(value);
    } else if (field === 'event') {
      event = value;
    } else if (field === 'id' && !value.includes('\0')) {
      id = value;
    }
  }
  return data.length === 0 ? null : { id, event, data: data.join('\n') };
}

/** Cuts the complete messages off the front of `text`; what is left is unfinished. */
export function splitMessages(text: string): { messages: SseMessage[]; rest: string } {
  // A lone \r at the very end may be the first half of \r\n: it waits for the next chunk.
  const normalised = text.replaceAll('\r\n', '\n').replaceAll(/\r(?!$)/g, '\n');
  const blocks = normalised.split('\n\n');
  const rest = blocks.pop() as string;
  const messages = blocks.flatMap((block) => parseBlock(block) ?? []);
  return { messages, rest };
}

/** Reads a response body to its end, yielding each message; cancels the body when the reader stops early. */
export async function* readMessages(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      const split = splitMessages(buffer);
      buffer = split.rest;
      yield* split.messages;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}
