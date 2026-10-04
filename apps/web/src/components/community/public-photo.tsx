/**
 * The public copy of an insight's photo, shown exactly where its owner chose to
 * show it: a published public post or a published atlas entry (v2 §19). The API
 * gives an absolute address under the configured public base (`photo_url`) or
 * nothing; a plain `<img>` loads it, lazily, from that host alone, and anything
 * that is not an http(s) address is not rendered at all. Hover changes nothing.
 */
export function PublicPhoto({ url, alt }: { url: string | null; alt: string }) {
  if (url === null || !/^https?:\/\//.test(url)) {
    return null;
  }
  return (
    <figure className="m-0 overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface">
      {/* The API's address is the source of truth; Next's image loader would add a request path of its own. */}
      {/* biome-ignore lint/performance/noImgElement: a plain img keeps the only request on the configured host. */}
      <img
        src={url}
        alt={alt}
        loading="lazy"
        decoding="async"
        className="block max-h-[70vh] w-full object-contain"
        data-testid="public-photo"
      />
    </figure>
  );
}
