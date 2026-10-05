import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';

/** A country the profile may declare (decision 67): its ISO2 code and the name to show. */
export interface CountryOption {
  code: string;
  name: string;
}

const byArabicName = new Intl.Collator('ar');

/** The countries of GeoNames, by the name shown (Arabic when GeoNames has it). */
export async function loadCountries(): Promise<Result<CountryOption[]>> {
  const result = await attempt(api.GET('/geo/countries'));
  if (!result.ok) {
    return result;
  }
  const options = result.data
    .map((country) => ({ code: country.iso2, name: country.label }))
    .sort((a, b) => byArabicName.compare(a.name, b.name));
  return { ...result, data: options };
}
