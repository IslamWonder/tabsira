// Answers for the API, served to the browser by the DevTools protocol, so the
// screenshots and the accessibility check show every screen in a known state
// without a database, a mail server or the consent routes (still being built).
// Sample data only: the names and texts below are examples, never shown as live.

import { progressSample, worldSample } from './world-samples.mjs';

const USER = {
  id: '6f9c1a52-3a51-4c8c-9f0e-1b2d3c4d5e6f',
  email: 'reader@example.com',
  display_name: 'قارئ تبصرة',
  is_admin: false,
  email_verified: false,
  has_password: true,
  providers: ['password'],
  created_at: '2026-10-04T08:00:00Z',
};

const PROFILE = {
  goals: ['reflection', 'curiosity'],
  knowledge_level: 'general',
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

// The policy texts are the API's to write; these stand in for them in pictures.
// Same shapes as the API's ConsentPolicyOut and CookieConsentOut.
const POLICY = {
  policy_version: '2026-10-04',
  reask_days: 180,
  categories: [
    {
      key: 'necessary',
      required: true,
      title: 'الضرورية',
      description: 'تحفظ دخولك وأمان الجلسة واختيارك هذا. لا تعمل تبصرة دونها، ولا تُستعمل للقياس.',
    },
    {
      key: 'analytics',
      required: false,
      title: 'قياس الاستعمال',
      description:
        'عدد الزيارات والصفحات والنقرات عبر Google Analytics، دون صورك ولا ما تكتبه ولا موقعك.',
    },
    {
      key: 'behaviour',
      required: false,
      title: 'السلوك والخرائط الحرارية',
      description: 'أين ينقر الزوار وكيف يمررون الصفحات، مع إخفاء كل نص يكتبونه.',
    },
  ],
};

export const CONSENT_ID = 'c0ffee00-1234-4abc-9def-0123456789ab';

/**
 * A choice recorded for real (all optional categories refused): the web server
 * checks the consent cookie with the API before it renders, so a sample id
 * would be asked again. API_INTERNAL_URL, else the API of `make dev`.
 */
export async function recordedConsentId() {
  const api = process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000';
  const response = await fetch(new URL('/consent', api), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ necessary: true, analytics: false, behaviour: false }),
  });
  if (!response.ok) {
    throw new Error(`Could not record a consent at ${api}: ${response.status}`);
  }
  return (await response.json()).consent_id;
}

const RECORD = {
  consent_id: CONSENT_ID,
  policy_version: POLICY.policy_version,
  decided_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 180 * 86_400_000).toISOString(),
  reask: false,
  categories: { necessary: true, analytics: false, behaviour: false },
};

function reply(status, body) {
  return { status, body };
}

/** The answer to one API request in a given state ('guest' or 'signed-in'). */
export function answer(method, pathname, state) {
  const route = `${method} ${pathname}`;
  if (route === 'GET /auth/providers') {
    return reply(200, {
      providers: [
        { id: 'password', available: true },
        { id: 'google', available: true },
      ],
    });
  }
  if (route === 'GET /auth/me') {
    return state === 'signed-in'
      ? reply(200, USER)
      : reply(401, { error: 'UNAUTHORIZED', detail: 'Sign in first.' });
  }
  if (route === 'GET /profile') {
    return reply(200, PROFILE);
  }
  if (route === 'GET /legal') {
    return reply(200, {
      terms_version: '2026-10-04',
      privacy_version: '2026-10-04',
      privacy_email: 'privacy@tabsira.me',
      support_email: 'support@tabsira.me',
    });
  }
  if (route === 'GET /consent/policy') {
    return reply(200, POLICY);
  }
  if (route === 'POST /consent' || route === `GET /consent/${CONSENT_ID}`) {
    return reply(200, RECORD);
  }
  if (route === 'GET /world') {
    return reply(200, worldSample());
  }
  if (route === 'GET /me/progress') {
    return reply(200, progressSample());
  }
  return reply(404, { error: 'NOT_FOUND', detail: `No sample answer for ${route}.` });
}

/**
 * Intercepts every request to `apiOrigin` and answers it from the samples.
 * CORS headers echo the page's origin, as the API does for its web app.
 */
export async function mockApi({ cdp, send }, { apiOrigin, siteOrigin, state }) {
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const url = new URL(request.url);
    const headers = [
      { name: 'Access-Control-Allow-Origin', value: siteOrigin },
      { name: 'Access-Control-Allow-Credentials', value: 'true' },
      { name: 'Access-Control-Allow-Headers', value: 'Content-Type, Accept' },
      { name: 'Access-Control-Allow-Methods', value: 'GET, POST, PATCH, DELETE' },
      { name: 'Content-Type', value: 'application/json' },
      { name: 'Cache-Control', value: 'no-store' },
    ];
    if (request.method === 'OPTIONS') {
      await send('Fetch.fulfillRequest', {
        requestId,
        responseCode: 204,
        responseHeaders: headers,
      });
      return;
    }
    const { status, body } = answer(request.method, url.pathname, state.value);
    await send('Fetch.fulfillRequest', {
      requestId,
      responseCode: status,
      responseHeaders: headers,
      body: Buffer.from(JSON.stringify(body)).toString('base64'),
    });
  });
  await send('Fetch.enable', { patterns: [{ urlPattern: `${apiOrigin}/*` }] });
}
