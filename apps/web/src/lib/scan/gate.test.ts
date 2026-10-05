import { describe, expect, it } from 'vitest';
import { networkFailure } from '@/lib/api/result';
import { accountRequired, profileRequired, signUpHref } from './gate';

const refused = (code: 'ACCOUNT_REQUIRED' | 'PROFILE_REQUIRED', status = 403) => ({
  ...networkFailure(),
  code,
  status,
});

describe('the gates of decision 63', () => {
  it('builds the sign-up address with the way back and the reason', () => {
    expect(signUpHref('/insight/1')).toBe('/signup?next=%2Finsight%2F1');
    expect(signUpHref('/world?a=1', 'scan')).toBe('/signup?next=%2Fworld%3Fa%3D1&reason=scan');
  });

  it('tells the guest refusal from the profile refusal, by code and status', () => {
    expect(accountRequired(refused('ACCOUNT_REQUIRED'))).toBe(true);
    expect(accountRequired(refused('PROFILE_REQUIRED'))).toBe(false);
    expect(accountRequired(refused('ACCOUNT_REQUIRED', 500))).toBe(false);
    expect(profileRequired(refused('PROFILE_REQUIRED'))).toBe(true);
    expect(profileRequired(refused('ACCOUNT_REQUIRED'))).toBe(false);
  });
});
