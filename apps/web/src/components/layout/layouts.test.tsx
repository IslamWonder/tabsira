import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  FeedLayout,
  MapLayout,
  PageContainer,
  ReadingLayout,
  SettingsLayout,
  StageLayout,
} from './layouts';

function order(...texts: string[]) {
  const nodes = texts.map((text) => screen.getByText(text));
  return nodes.every(
    (node, index) =>
      index === 0 ||
      (nodes[index - 1] as Node).compareDocumentPosition(node) === Node.DOCUMENT_POSITION_FOLLOWING
  );
}

describe('layout primitives', () => {
  it('PageContainer centres content at most 1440 px wide', () => {
    render(<PageContainer className="extra">content</PageContainer>);
    expect(screen.getByText('content')).toHaveClass('max-w-[1440px]', 'extra');
  });

  it('StageLayout puts the panel first and names the stage', () => {
    render(
      <StageLayout
        panel={<p>panel</p>}
        stage={<p>stage</p>}
        stageLabel="المشهد"
        stageClassName="h-72"
      />
    );
    expect(order('panel', 'stage')).toBe(true);
    const stage = screen.getByRole('region', { name: 'المشهد' });
    expect(stage).toHaveTextContent('stage');
    expect(stage).toHaveClass('h-72');
  });

  it('ReadingLayout keeps the photo first, the column next, and pins its footer', () => {
    const { rerender } = render(
      <ReadingLayout media={<figure>photo</figure>} footer={<span>actions</span>}>
        <p>text</p>
      </ReadingLayout>
    );
    expect(order('photo', 'text', 'actions')).toBe(true);
    expect(screen.getByRole('article')).toHaveTextContent('textactions');
    expect(screen.getByText('actions').parentElement).toHaveClass('sticky', 'bottom-0');
    rerender(
      <ReadingLayout media={<figure>photo</figure>}>
        <p>text</p>
      </ReadingLayout>
    );
    expect(screen.getByRole('article')).toHaveTextContent(/^text$/);
  });

  it('MapLayout puts the list before the named map', () => {
    render(<MapLayout panel="list" map="map" mapLabel="الخريطة" mapClassName="hidden" />);
    expect(order('list', 'map')).toBe(true);
    expect(screen.getByRole('complementary')).toHaveTextContent('list');
    expect(screen.getByRole('region', { name: 'الخريطة' })).toHaveClass('hidden');
  });

  it('FeedLayout puts the tabs before a feed column at most 640 px wide', () => {
    render(<FeedLayout aside="tabs" feed="feed" />);
    expect(order('tabs', 'feed')).toBe(true);
    expect(screen.getByText('feed')).toHaveClass('max-w-[40rem]');
  });

  it('SettingsLayout hides the section list on phones', () => {
    render(<SettingsLayout nav="sections">settings</SettingsLayout>);
    expect(order('sections', 'settings')).toBe(true);
    expect(screen.getByText('sections')).toHaveClass('hidden', 'tablet:block');
  });
});
