import type { Profile } from '@/account/profile';
import type { User } from '@/account/session';
import type { ConsentPolicy, ConsentRecord } from '@/consent/contract';

/** Sample answers of the API, in the shapes it publishes, for unit tests only. */

export const USER: User = {
  id: '6f9c1a52-3a51-4c8c-9f0e-1b2d3c4d5e6f',
  email: 'reader@example.com',
  display_name: '[اسم القارئ]',
  is_admin: false,
  email_verified: true,
  has_password: true,
  providers: ['password'],
  created_at: '2026-10-04T08:00:00Z',
};

export const PROFILE: Profile = {
  goals: [],
  knowledge_level: 'unknown',
  age_range: 'unknown',
  religious_background: 'unknown',
  gender: 'unknown',
  language: 'ar',
  personalization_enabled: true,
  memory_enabled: true,
  photo_storage_consent: false,
  theme: 'system',
  sound_enabled: false,
  consent_version: null,
  updated_at: '2026-10-04T08:00:00Z',
};

export const POLICY: ConsentPolicy = {
  policy_version: '2026-10-04',
  reask_days: 180,
  categories: [
    { key: 'necessary', required: true, title: '[الضرورية]', description: '[وصف الضرورية]' },
    { key: 'analytics', required: false, title: '[القياس]', description: '[وصف القياس]' },
    { key: 'behaviour', required: false, title: '[السلوك]', description: '[وصف السلوك]' },
  ],
};

export const RECORD: ConsentRecord = {
  consent_id: 'c0ffee00-1234-4abc-9def-0123456789ab',
  policy_version: '2026-10-04',
  decided_at: '2026-10-04T09:30:00Z',
  expires_at: '2027-04-02T09:30:00Z',
  reask: false,
  categories: { necessary: true, analytics: true, behaviour: false },
};
