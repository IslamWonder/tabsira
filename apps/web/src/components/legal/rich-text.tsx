import { Fragment, type ReactNode } from 'react';

// An address, or a run of Latin words (a product name). The first group is an address.
const TOKEN =
  /([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|([A-Za-z][A-Za-z0-9]*(?: [A-Za-z][A-Za-z0-9]*)*)/g;

/**
 * Plain text with two touches the Arabic page needs: an e-mail address becomes
 * a mailto link set left to right, and a Latin name is isolated with <bdi> so
 * it cannot reorder the Arabic around it (docs/SEO.md §4).
 */
export function RichText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const at = match.index;
    if (at > last) {
      parts.push(<Fragment key={`t${last}`}>{text.slice(last, at)}</Fragment>);
    }
    const [token, address] = match;
    parts.push(
      address === undefined ? (
        <bdi key={`b${at}`}>{token}</bdi>
      ) : (
        <a
          key={`a${at}`}
          href={`mailto:${token}`}
          dir="ltr"
          className="font-medium text-link underline"
        >
          {token}
        </a>
      )
    );
    last = at + token.length;
  }
  if (last < text.length) {
    parts.push(<Fragment key={`t${last}`}>{text.slice(last)}</Fragment>);
  }
  return <>{parts}</>;
}
