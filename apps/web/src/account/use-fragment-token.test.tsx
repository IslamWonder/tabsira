import { render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { useFragmentToken } from './use-fragment-token';

function Probe() {
  const link = useFragmentToken();
  return <p>{link.status === 'found' ? link.token : link.status}</p>;
}

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('useFragmentToken', () => {
  it('reads the token once, even twice-run in development, and clears it from the address', () => {
    const token = 'k'.repeat(43);
    window.history.replaceState(null, '', `/reset-password?x=1#token=${token}`);
    render(
      <StrictMode>
        <Probe />
      </StrictMode>
    );
    expect(screen.getByText(token)).toBeInTheDocument();
    expect(window.location.hash).toBe('');
    expect(window.location.search).toBe('?x=1');
  });

  it('says when the link carries no token', () => {
    window.history.replaceState(null, '', '/verify-email');
    render(<Probe />);
    expect(screen.getByText('missing')).toBeInTheDocument();
  });
});
