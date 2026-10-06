/**
 * Structured data for crawlers. Built from constants and, on a public insight, from the
 * API's published fields (title, public name); never from the request.
 */
export function JsonLd({ data }: Readonly<{ data: Record<string, unknown> }>) {
  // "<" is escaped so no value could ever close the script element.
  const json = JSON.stringify(data).replaceAll(/</g, String.raw`\u003c`);
  return (
    // biome-ignore lint/security/noDangerouslySetInnerHtml: serialised constants with "<" escaped; JSON-LD needs the raw text.
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />
  );
}
