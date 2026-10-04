const MAX_PUBLIC_ID = 2n ** 63n - 1n;

/** A public id as the API writes it in a path: a positive decimal number of at most 19 digits (apps/api/src/schemas/public_id.py). */
export function isPublicId(value: string): boolean {
  // 19 digits can exceed the API's bigint range (2^63 - 1), which it refuses with 422.
  return /^[1-9][0-9]{0,18}$/.test(value) && BigInt(value) <= MAX_PUBLIC_ID;
}
