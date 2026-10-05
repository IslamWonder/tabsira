import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorReporting } from './error-reporting';

const report = vi.hoisted(() => ({ installErrorReporting: vi.fn() }));
vi.mock('@/lib/errors/report', () => report);

beforeEach(() => {
  report.installErrorReporting.mockClear();
});

describe('ErrorReporting', () => {
  it('starts reporting in a production build and renders nothing', () => {
    const { container } = render(<ErrorReporting enabled />);
    expect(report.installErrorReporting).toHaveBeenCalledOnce();
    expect(container).toBeEmptyDOMElement();
  });

  it('stays off in development', () => {
    render(<ErrorReporting />);
    expect(report.installErrorReporting).not.toHaveBeenCalled();
  });
});
