import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FocusPanel } from './focus-picker';

describe('FocusPanel', () => {
  it('says the scene found nothing to choose, and still lets the reader go back', () => {
    render(
      <FocusPanel
        entities={[]}
        selectedId={undefined}
        onSelect={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        acting={false}
        error={null}
      />
    );
    expect(screen.getByText(/لم نتعرف على شيء يمكن اختياره هنا/)).toBeInTheDocument();
    expect(screen.queryByRole('list')).toBeNull();
    expect(screen.getByRole('button', { name: 'انظر إلى هذا' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'ارجع' })).toBeEnabled();
  });
});
