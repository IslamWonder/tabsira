import { Fragment, type ReactNode } from 'react';

// A web address, an e-mail address, or a run of Latin words (a product name).
// A web address ends before a space, an Arabic comma or a closing bracket, and
// leaves out a final full stop or comma, which belong to the sentence.
const TOKEN =
  /(https?:\/\/[^\s\u060C)]*[^\s\u060C).,])|([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|([A-Za-z][A-Za-z0-9]*(?: [A-Za-z][A-Za-z0-9]*)*)/g;

/**
 * Plain text with three touches the Arabic page needs: a web address becomes a
 * link and an e-mail address a mailto link, both set left to right, and a Latin
 * name is isolated with <bdi> so it cannot reorder the Arabic around it
 * (docs/SEO.md §4).
 */
export function RichText({ text }: Readonly<{ text: string }>) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const at = match.index;
    if (at > last) {
      parts.push(<Fragment key={`t${last}`}>{text.slice(last, at)}</Fragment>);
    }
    const [token, url, address] = match;
    parts.push(
      url !== undefined ? (
        <a key={`u${at}`} href={url} dir="ltr" className="font-medium text-link underline">
          {url}
        </a>
      ) : address === undefined ? (
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
