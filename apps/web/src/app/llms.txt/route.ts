import { llmsTxt } from '@/lib/llms';

const HEADERS = { 'Content-Type': 'text/plain; charset=utf-8' } as const;

export function GET(): Response {
  return new Response(llmsTxt(), { headers: HEADERS });
}
