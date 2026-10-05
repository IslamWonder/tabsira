import { describe, expect, it } from 'vitest';
import { ar } from './ar';

describe('the insights of the world and of the top bar', () => {
  it('count them the Arabic way, singly in the top bar summary and in the world', () => {
    expect(ar.nav.progress.insights(1)).toBe('بصيرة واحدة');
    expect(ar.nav.progress.label(1, 0)).toBe('تقدّمك: بصيرة واحدة. افتح تمرينك');
    expect(ar.world.count(1)).toBe('بصيرة واحدة');
    expect(ar.world.landmark('[موضع]', 3, '[عنوان]')).toBe('افتح ما تعلّمته في [موضع]: 3 بصائر');
  });
});

describe('the profile flow', () => {
  it('says which question of how many the reader is at', () => {
    expect(ar.profile.flow.progress(2, 5)).toBe('السؤال 2 من 5');
  });
});

describe('the Arabic counted nouns', () => {
  it('count minutes: one, two, three to ten, eleven and more', () => {
    expect(ar.errors.minutes(0)).toBe('دقيقة');
    expect(ar.errors.minutes(1)).toBe('دقيقة');
    expect(ar.errors.minutes(2)).toBe('دقيقتين');
    expect(ar.errors.minutes(10)).toBe('10 دقائق');
    expect(ar.errors.minutes(11)).toBe('11 دقيقة');
    expect(ar.errors.rateLimited(ar.errors.minutes(3))).toBe(
      'محاولات كثيرة في وقت قصير. أعد المحاولة بعد 3 دقائق.'
    );
  });

  it('count the insights of the atlas', () => {
    expect(ar.atlas.count(0)).toBe('لا بصائر');
    expect(ar.atlas.count(1)).toBe('بصيرة واحدة');
    expect(ar.atlas.count(2)).toBe('بصيرتان');
    expect(ar.atlas.count(10)).toBe('10 بصائر');
    expect(ar.atlas.count(11)).toBe('11 بصيرة');
    expect(ar.atlas.cluster(12)).toBe('مجموعة من 12 بصائر، قرّب لتفصلها');
    expect(ar.atlas.marker('[عنوان]')).toBe('افتح [عنوان]');
  });

  it('count the likes and the comments of a post', () => {
    expect(ar.community.post.commentCount(0)).toBe('لا تعليقات');
    expect(ar.community.post.commentCount(1)).toBe('تعليق واحد');
    expect(ar.community.post.commentCount(2)).toBe('تعليقان');
    expect(ar.community.post.commentCount(10)).toBe('10 تعليقات');
    expect(ar.community.post.commentCount(11)).toBe('11 تعليقًا');
  });

  it('name distances and dates', () => {
    expect(ar.atlas.camera.meters(80)).toBe('80 م');
    expect(ar.atlas.camera.kilometers('1.2')).toBe('1.2 كم');
    expect(ar.community.post.publishedAt('[تاريخ]')).toBe('نُشر في [تاريخ]');
    expect(ar.community.post.createdAt('[تاريخ]')).toBe('أُنشئ في [تاريخ]');
  });
});
