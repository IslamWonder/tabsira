import { describe, expect, it } from 'vitest';
import { ar } from './ar';

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
