import { describe, expect, it } from 'vitest';
import { featureStories, type LandingFeatures } from './landing-model';

const ALL_ON: LandingFeatures = {
  chat: true,
  world: true,
  treasure: true,
  social: true,
  atlas: true,
  cameraDiscovery: true,
  photoStorage: true,
  canonicalVerify: true,
};

const ALL_OFF: LandingFeatures = Object.fromEntries(
  Object.keys(ALL_ON).map((key) => [key, false])
) as unknown as LandingFeatures;

const titles = (features: LandingFeatures) =>
  featureStories(features).map((story) => [story.id, story.benefits.map((item) => item.icon)]);

describe('the landing stories', () => {
  it('announce everything that is on, with a way into each', () => {
    const stories = featureStories(ALL_ON);

    expect(titles(ALL_ON)).toEqual([
      ['meaning', ['lens', 'chat', 'verify']],
      ['world', ['world', 'atlas', 'around']],
      ['community', ['treasure', 'community', 'photos']],
    ]);
    expect(stories.map((story) => story.action)).toEqual([
      { kind: 'example', label: 'جرّب بصيرة الآن', icon: 'lens' },
      { kind: 'link', href: '/atlas', label: 'افتح الأطلس', icon: 'atlas' },
      { kind: 'link', href: '/community', label: 'اكتشف تواصل', icon: 'community' },
    ]);
  });

  it.each(Object.keys(ALL_ON) as (keyof LandingFeatures)[])(
    'drop what %s brings when it is off, and keep the core journey',
    (flag) => {
      const stories = featureStories({ ...ALL_ON, [flag]: false });
      const meaning = stories.find((story) => story.id === 'meaning');

      expect(meaning?.action?.kind).toBe('example');
      expect(meaning?.benefits[0]?.icon).toBe('lens');
      expect(stories.every((story) => story.benefits.length > 0)).toBe(true);
    }
  );

  it('fall back to the world when the atlas or the network is off, and to nothing without it', () => {
    const noAtlas = featureStories({ ...ALL_ON, atlas: false, social: false });
    expect(noAtlas.map((story) => story.action)).toContainEqual({
      kind: 'link',
      href: '/world',
      label: 'افتح عالمي',
      icon: 'world',
    });
    expect(titles({ ...ALL_ON, atlas: false })[1]).toEqual(['world', ['world']]);

    const alone = featureStories({ ...ALL_OFF, photoStorage: true });
    expect(alone.map((story) => [story.id, story.action])).toEqual([
      ['meaning', { kind: 'example', label: 'جرّب بصيرة الآن', icon: 'lens' }],
      ['community', null],
    ]);
  });

  it('never promise the treasure without the world it waits in', () => {
    expect(titles({ ...ALL_ON, world: false })[2]).toEqual(['community', ['community', 'photos']]);
  });

  it('keep the core story alone when every optional feature is off', () => {
    expect(titles(ALL_OFF)).toEqual([['meaning', ['lens']]]);
  });
});
