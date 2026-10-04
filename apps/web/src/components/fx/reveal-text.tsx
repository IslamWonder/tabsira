import { cx } from '@/lib/cx';

export interface RevealTextProps {
  /** Interface copy only. Never scripture: Quran and hadith text stays still (DESIGN_DECISION.md). */
  text: string;
  as?: 'h1' | 'h2' | 'h3' | 'p' | 'span';
  /** Seconds before the first word. */
  delay?: number;
  /** Seconds between two words. */
  stagger?: number;
  className?: string;
}

/**
 * A line that appears word by word, each word rising out of a soft blur, in
 * reading order. Arabic letters never join across a space, so splitting on
 * spaces keeps every word whole. Screen readers get the sentence once, intact.
 * Under reduced motion every word is simply there.
 */
export function RevealText({
  text,
  as: Tag = 'p',
  delay = 0,
  stagger = 0.07,
  className,
}: RevealTextProps) {
  const words = Array.from(text.matchAll(/\S+/g), (match) => ({ word: match[0], at: match.index }));
  return (
    <Tag className={cx('m-0', className)}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {words.map(({ word, at }, index) => (
          <span key={at}>
            <span className="fx-word" style={{ animationDelay: `${delay + index * stagger}s` }}>
              {word}
            </span>
            {index < words.length - 1 ? ' ' : null}
          </span>
        ))}
      </span>
    </Tag>
  );
}
