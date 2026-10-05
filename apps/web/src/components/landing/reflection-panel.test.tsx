import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReflectionPanel } from './reflection-panel';

describe('ReflectionPanel', () => {
  it('frames the reflection with its emblem and an invitation to read slowly', () => {
    render(<ReflectionPanel glimpse="[تأمّل]" smallStep={{ label: '[خطوة]', text: '[افعل]' }} />);
    const panel = screen.getByRole('region', { name: 'التأمّل' });
    expect(panel).toHaveTextContent('خذ لحظة، واقرأ على مهل.');
    expect(panel).toHaveTextContent('[تأمّل]');
    expect(screen.getByText('[خطوة]')).toBeInTheDocument();
    expect(screen.getByText('[افعل]')).toBeInTheDocument();
    // The emblems are decoration: their names are the words beside them.
    for (const svg of panel.querySelectorAll('svg')) {
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    }
  });

  it('shows the reflection alone when there is no small step', () => {
    render(<ReflectionPanel glimpse="[تأمّل]" smallStep={null} />);
    const panel = screen.getByRole('region', { name: 'التأمّل' });
    expect(panel).toHaveTextContent('[تأمّل]');
    expect(panel.querySelector('.border-dashed')).toBeNull();
  });
});
