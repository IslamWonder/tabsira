import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DisclosureLine } from './disclosure-line';

describe('DisclosureLine', () => {
  it('says what the master prompt fixes, word for word', () => {
    render(<DisclosureLine className="extra" />);
    const line = screen.getByText('تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا');
    expect(line).toHaveClass('extra');
  });
});
