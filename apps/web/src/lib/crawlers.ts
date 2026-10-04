/**
 * The AI agents robots.txt names one by one (docs/SEO.md §1). Policy: all
 * allowed; the owners may restrict the training crawlers later by moving a
 * name out of this list into a disallow group.
 */
export const AI_AGENTS = [
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  'ClaudeBot',
  'Claude-SearchBot',
  'Claude-User',
  'Google-Extended',
  'GoogleOther',
  'PerplexityBot',
  'Perplexity-User',
  'Bingbot',
  'Applebot-Extended',
  'meta-externalagent',
  'Amazonbot',
  'CCBot',
  'DuckAssistBot',
  'MistralAI-User',
] as const;
