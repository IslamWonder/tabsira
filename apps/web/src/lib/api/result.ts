import type { components } from './schema';

export type ApiErrorCode = components['schemas']['ErrorCode'];
export type FieldError = components['schemas']['FieldError'];

/**
 * Every way a call can fail: an error code the API answered, or no answer at
 * all. LEGAL_ACCEPTANCE_REQUIRED is decision 35's refusal, named here until
 * the API that sends it is in the generated schema. ACCOUNT_REQUIRED and PROFILE_REQUIRED are
 * decision 64's two 403s, TUTORIAL_CLOSED its refusal of the example to an account with an
 * insight of its own (the codes are compared in capitals, see `attempt`). TURNSTILE_FAILED is the
 * 403 of a missing or bad Turnstile token (decision 56), named the same way.
 */
export type FailureCode =
  | ApiErrorCode
  | 'LEGAL_ACCEPTANCE_REQUIRED'
  | 'ACCOUNT_REQUIRED'
  | 'PROFILE_REQUIRED'
  | 'TUTORIAL_CLOSED'
  | 'TURNSTILE_FAILED'
  | 'NETWORK';

export interface Failure {
  ok: false;
  code: FailureCode;
  /** The HTTP status, 0 when nothing answered. */
  status: number;
  /** Only for VALIDATION_ERROR: the refused fields, by location. */
  fields: readonly FieldError[];
  /** Seconds to wait before trying again, from Retry-After, when the API said so. */
  retryAfter: number | null;
}

export interface Success<T> {
  ok: true;
  data: T;
  status: number;
}

export type Result<T> = Success<T> | Failure;

/** What openapi-fetch resolves to; it rejects only when the request never got an answer. */
interface FetchOutcome<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

const CODE_BY_STATUS: Readonly<Record<number, ApiErrorCode>> = {
  400: 'BAD_REQUEST',
  401: 'UNAUTHORIZED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  422: 'VALIDATION_ERROR',
  429: 'RATE_LIMITED',
  503: 'SERVICE_UNAVAILABLE',
};

function isErrorBody(value: unknown): value is components['schemas']['ErrorResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { error?: unknown }).error === 'string'
  );
}

function retryAfter(response: Response): number | null {
  const seconds = Number.parseInt(response.headers.get('Retry-After') ?? '', 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

/** A failure the API never answered: offline, DNS, TLS, CORS, a dropped connection. */
export function networkFailure(): Failure {
  return { ok: false, code: 'NETWORK', status: 0, fields: [], retryAfter: null };
}

/**
 * Turns an openapi-fetch call into a result the interface can branch on: the
 * data, or one stable code. A body that is not the API's error shape (a proxy's
 * HTML page, say) is named by its status, so every screen has an honest message.
 */
export async function attempt<T>(call: Promise<FetchOutcome<T>>): Promise<Result<T>> {
  let outcome: FetchOutcome<T>;
  try {
    outcome = await call;
  } catch {
    return networkFailure();
  }
  const { response } = outcome;
  if (response.ok) {
    return { ok: true, data: outcome.data as T, status: response.status };
  }
  const body = outcome.error;
  // Codes are compared in capitals, whatever case a route answers in.
  const code = isErrorBody(body)
    ? (body.error.toUpperCase() as FailureCode)
    : (CODE_BY_STATUS[response.status] ??
      (response.status >= 500 ? 'INTERNAL_ERROR' : 'HTTP_ERROR'));
  return {
    ok: false,
    code,
    status: response.status,
    fields: isErrorBody(body) ? (body.fields ?? []) : [],
    retryAfter: retryAfter(response),
  };
}

/** Whether the API refused this field (its location ends with the field's name). */
export function fieldRefused(failure: Failure, field: string): boolean {
  return failure.fields.some((item) => item.loc.at(-1) === field);
}
