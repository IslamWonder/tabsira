import { describe, expect, it } from 'vitest';
import { messages } from '@/messages';
import { failureMessage } from './failure-message';
import { attempt, type Failure, fieldRefused, networkFailure } from './result';

function outcome(status: number, error?: unknown, headers: Record<string, string> = {}) {
  return Promise.resolve({
    data: undefined,
    error,
    response: new Response(null, { status, headers }),
  });
}

function failure(code: Failure['code'], extra: Partial<Failure> = {}): Failure {
  return { ok: false, code, status: 400, fields: [], retryAfter: null, ...extra };
}

describe('attempt', () => {
  it('passes the data of a success through', async () => {
    const result = await attempt(
      Promise.resolve({ data: { a: 1 }, response: new Response(null, { status: 200 }) })
    );
    expect(result).toEqual({ ok: true, data: { a: 1 }, status: 200 });
  });

  it('names a request that got no answer NETWORK', async () => {
    expect(await attempt(Promise.reject(new TypeError('Failed to fetch')))).toEqual(
      networkFailure()
    );
  });

  it('keeps the API code, the refused fields and Retry-After', async () => {
    const fields = [{ loc: ['body', 'email'], message: 'bad', type: 'value_error' }];
    const result = await attempt(
      outcome(429, { error: 'RATE_LIMITED', detail: 'x', fields }, { 'Retry-After': '900' })
    );
    expect(result).toEqual({
      ok: false,
      code: 'RATE_LIMITED',
      status: 429,
      fields,
      retryAfter: 900,
    });
    expect(fieldRefused(result as Failure, 'email')).toBe(true);
    expect(fieldRefused(result as Failure, 'password')).toBe(false);
    const bare = await attempt(outcome(401, { error: 'UNAUTHORIZED', detail: 'x' }));
    expect(bare).toMatchObject({ code: 'UNAUTHORIZED', fields: [], retryAfter: null });
  });

  it('names a body that is not the API error shape by its status', async () => {
    expect(await attempt(outcome(409, '<html>'))).toMatchObject({ code: 'CONFLICT' });
    expect(await attempt(outcome(502, null))).toMatchObject({ code: 'INTERNAL_ERROR' });
    expect(await attempt(outcome(418, { nope: true }))).toMatchObject({ code: 'HTTP_ERROR' });
    expect(await attempt(outcome(400, null, { 'Retry-After': 'soon' }))).toMatchObject({
      code: 'BAD_REQUEST',
      retryAfter: null,
    });
  });
});

describe('failureMessage', () => {
  it('has a sentence for each code the screens meet', () => {
    expect(failureMessage(failure('NETWORK'))).toBe(messages.errors.network);
    expect(failureMessage(failure('INVALID_CREDENTIALS'))).toBe(messages.errors.invalidCredentials);
    expect(failureMessage(failure('EMAIL_TAKEN'))).toBe(messages.errors.emailTaken);
    expect(failureMessage(failure('CONSENT_NOT_ALLOWED'))).toBe(messages.errors.consentNotAllowed);
  });

  it('says how long to wait when the API said so, and puts other faults on our side', () => {
    expect(failureMessage(failure('RATE_LIMITED', { retryAfter: 900 }))).toBe(
      'محاولات كثيرة في وقت قصير. أعد المحاولة بعد 15 دقيقة.'
    );
    expect(failureMessage(failure('RATE_LIMITED'))).toBe(messages.errors.rateLimitedSoon);
    expect(failureMessage(failure('INTERNAL_ERROR'))).toBe(messages.errors.server);
  });

  it('does not call the legal refusal an error: the gate opens over the screen', () => {
    expect(failureMessage(failure('LEGAL_ACCEPTANCE_REQUIRED', { status: 403 }))).toBe(
      messages.errors.legalRequired
    );
    expect(failureMessage(failure('LEGAL_ACCEPTANCE_REQUIRED', { status: 422 }))).toBe(
      messages.errors.legalStale
    );
  });

  it('counts minutes the Arabic way', () => {
    expect([1, 2, 3, 10, 11, 15].map(messages.errors.minutes)).toEqual([
      'دقيقة',
      'دقيقتين',
      '3 دقائق',
      '10 دقائق',
      '11 دقيقة',
      '15 دقيقة',
    ]);
  });
});
