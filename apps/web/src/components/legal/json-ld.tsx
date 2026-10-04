/** Structured data for crawlers; the data is built from constants, never from a request. */
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  // "<" is escaped so no value could ever close the script element.
  const json = JSON.stringify(data).replace(/</g, '\\u003c');
  return (
    // biome-ignore lint/security/noDangerouslySetInnerHtml: serialised constants with "<" escaped; JSON-LD needs the raw text.
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />
  );
}
