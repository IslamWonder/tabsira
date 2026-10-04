import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ANSWERS_STORAGE_KEY,
  clearDeviceAnswers,
  deviceQuestionsAsked,
  markDeviceQuestionsAsked,
  readDeviceAnswers,
  rememberDeviceAnswer,
} from './device-answers';

beforeEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe('device answers of a guest', () => {
  it('starts with nothing asked and nothing answered', () => {
    expect(deviceQuestionsAsked()).toBe(false);
    expect(readDeviceAnswers()).toBeNull();
  });

  it('keeps each answer, merged, and counts the questions as asked', () => {
    rememberDeviceAnswer({ goals: ['reflection'] });
    rememberDeviceAnswer({ age_range: '25_39' });
    expect(deviceQuestionsAsked()).toBe(true);
    expect(readDeviceAnswers()).toEqual({ goals: ['reflection'], age_range: '25_39' });
  });

  it('marks the questions asked with no answer, keeps earlier ones, and clears on demand', () => {
    markDeviceQuestionsAsked();
    expect(readDeviceAnswers()).toEqual({});
    rememberDeviceAnswer({ knowledge_level: 'general' });
    markDeviceQuestionsAsked();
    expect(readDeviceAnswers()).toEqual({ knowledge_level: 'general' });
    clearDeviceAnswers();
    expect(deviceQuestionsAsked()).toBe(false);
  });

  it('treats a damaged or foreign value as never asked', () => {
    window.localStorage.setItem(ANSWERS_STORAGE_KEY, '{not json');
    expect(deviceQuestionsAsked()).toBe(false);
    window.localStorage.setItem(ANSWERS_STORAGE_KEY, '"text"');
    expect(readDeviceAnswers()).toBeNull();
    window.localStorage.setItem(ANSWERS_STORAGE_KEY, '{"asked":true}');
    expect(readDeviceAnswers()).toBeNull();
    window.localStorage.setItem(ANSWERS_STORAGE_KEY, '{"answers":null}');
    expect(readDeviceAnswers()).toEqual({});
  });

  it('survives a storage that refuses to write or clear', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('full');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('locked');
    });
    expect(() => rememberDeviceAnswer({ goals: [] })).not.toThrow();
    expect(() => clearDeviceAnswers()).not.toThrow();
    expect(deviceQuestionsAsked()).toBe(false);
  });
});
