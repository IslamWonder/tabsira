import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { loadCountries } from './countries';

const country = (iso2: string, label: string) => ({
  iso2,
  iso3: null,
  name: iso2,
  name_ar: null,
  label,
  capital: null,
  continent: null,
  flag_emoji: null,
  population: null,
});

describe('loadCountries', () => {
  it('lists the GeoNames countries by the name shown, in Arabic order', async () => {
    mockApi({
      'GET /geo/countries': {
        body: [country('TN', 'تونس'), country('DZ', 'الجزائر'), country('FR', 'France')],
      },
    });
    const result = await loadCountries();
    expect(result.ok && result.data).toEqual([
      { code: 'DZ', name: 'الجزائر' },
      { code: 'TN', name: 'تونس' },
      { code: 'FR', name: 'France' },
    ]);
  });

  it('passes a failure on', async () => {
    mockApi({ 'GET /geo/countries': apiError(500, 'INTERNAL_ERROR') });
    expect(await loadCountries()).toMatchObject({ ok: false, code: 'INTERNAL_ERROR' });
  });
});
