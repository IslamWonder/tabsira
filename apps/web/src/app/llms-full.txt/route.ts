import { llmsFullTxt } from '@/lib/llms';

const HEADERS = { 'Content-Type': 'text/plain; charset=utf-8' } as const;

export function GET(): Response {
  return new Response(llmsFullTxt(), { headers: HEADERS });
}
