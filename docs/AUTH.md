# Accounts and sessions: the contract

What the web app can rely on, and what the API requires of it. Code: `apps/api/src/routers/auth*.py`, `google_auth.py`, `profile.py`, `account.py`; services in `apps/api/src/services`. What is stored, and why, is in `docs/PRIVACY.md`.

## Sessions

- A session lives in PostgreSQL, in the `sessions` table: the SHA-256 hash of a random 256-bit token, the user, the creation, last-seen and expiry times, a keyed hash of the IP address and the user agent. There is no Redis.
- The browser gets one cookie, `SESSION_COOKIE_NAME` (default `__Secure-tabsira_session`): httpOnly, Secure, SameSite=Lax, path `/`, `Max-Age` of `SESSION_TTL_DAYS` (30). Its domain is `SESSION_COOKIE_DOMAIN`: `.tabsira.test` in development and `.tabsira.me` in production, so the web app and the API on sibling subdomains share it. Production refuses a `.test` domain.
- The expiry is fixed at sign-in; there is no sliding renewal. Signing out, resetting a password or deleting the account deletes the rows, so a copied cookie is dead at once. Every sign-in issues a new token and ends the session the browser held (no session fixation).
- The web app calls the API with `credentials: "include"`; `CORS_ORIGINS` lists the web origin.

## CSRF: the Origin check

SameSite=Lax keeps the cookie off cross-site POSTs, but the web app and the API are sibling subdomains of one site, and Lax does not stop a request from another sibling. So every `POST`, `PUT`, `PATCH` and `DELETE` also passes `OriginCheckMiddleware` (`src/middleware/origin_check.py`):

- With an `Origin` header (a browser always sends one on these methods) it must be one of `CORS_ORIGINS` or the API's own address (`API_URL`, for the interactive docs). `Origin: null` is refused.
- With no `Origin` but a `Sec-Fetch-Site` header, only `same-origin` and `none` pass.
- With neither, the caller is not a browser (curl, a test, a server) and no cookie rides along on its own, so the request passes.

A refusal is `403 {"error": "ORIGIN_NOT_ALLOWED"}`. Reads are never checked. Responses of `/auth`, `/profile`, `/consents`, `/consent` (cookie consent, see `docs/PRIVACY.md`) and `/account` carry `Cache-Control: no-store`.

## Routes

| Route                            | Needs   | Notes                                                                                                                                                                       |
| -------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /auth/signup`              | nothing | 201, signs in, mails a verification link. Password 10 characters or more and at most 72 bytes (Arabic letters take two). 409 `EMAIL_TAKEN`. Limited per IP and per address. |
| `POST /auth/login`               | nothing | 401 `INVALID_CREDENTIALS` for a wrong address or password alike; 403 `ACCOUNT_DISABLED` only after the right password. Failed attempts are limited per IP and per address.  |
| `POST /auth/logout`              | nothing | 204; safe to repeat.                                                                                                                                                        |
| `GET /auth/me`                   | session | The account. Never the private profile fields.                                                                                                                              |
| `GET /auth/providers`            | nothing | Whether `password` and `google` are available.                                                                                                                              |
| `POST /auth/verify-email`        | nothing | `{token}`; 200, or 400 `INVALID_TOKEN` for any bad token.                                                                                                                   |
| `POST /auth/resend-verification` | nothing | `{email}`; always 202. Limited per IP and per address.                                                                                                                      |
| `POST /auth/forgot-password`     | nothing | `{email}`; always 202. Limited per IP and per address.                                                                                                                      |
| `POST /auth/reset-password`      | nothing | `{token, password}`; 200 or 400 `INVALID_TOKEN`. Ends every other session, and proves the address. It does not sign anyone in.                                              |
| `GET /auth/google/start`         | nothing | 302 to Google; `?next=/path` is where to land afterwards (a path in the web app only).                                                                                      |
| `GET /auth/google/callback`      | cookie  | 302 to the web app. See below.                                                                                                                                              |
| `GET /profile`, `PATCH /profile` | session | Partial update; an unanswered field is `unknown`. A null is refused. The three consent switches are not patchable.                                                          |
| `POST /consents`                 | session | `{kind, version, granted}`; appends to the history and updates the matching switch. 403 `CONSENT_NOT_ALLOWED` for photo storage when the age range is `under_13`.           |
| `GET /account/export`            | session | Everything the account owns, as a JSON download.                                                                                                                            |
| `DELETE /account`                | nothing | 204; deletes the account and everything it owns. Idempotent: with no session it still answers 204.                                                                          |

The goals are stored as `discover_islam`, `reflection`, `learn_quran_sunnah`, `live_values`, `research`, `teaching` and `curiosity`; the Arabic labels (التعرّف إلى الإسلام، التفكر، تعلّم القرآن والسنة، العمل بالقيم، البحث، التعليم، الفضول والاستكشاف) belong to the web app's messages.

## Google

OpenID Connect, authorization code flow with PKCE (S256). `start` stores a state, a code verifier and a nonce on the server for `GOOGLE_STATE_TTL_SECONDS` and sets a short-lived cookie that ties the flow to the browser, so a callback link handed to someone else is refused. The callback exchanges the code, checks the ID token's signature against Google's published keys (cached), its issuer, audience, expiry and nonce, and requires a verified address. With `GOOGLE_CLIENT_ID` empty both routes answer `503 GOOGLE_NOT_CONFIGURED` and `/auth/providers` reports Google unavailable.

Every outcome is a redirect. Success lands on `SITE_URL` plus the `next` path (default `/`). A failure lands on `SITE_URL/login?error=<code>`:

| Code               | Meaning                                                                          |
| ------------------ | -------------------------------------------------------------------------------- |
| `google_state`     | The sign-in is unknown, expired, used already, or was started by another browser |
| `google_denied`    | The person declined at Google                                                    |
| `google_failed`    | Google's answer could not be completed or trusted                                |
| `account_disabled` | The account behind the identity is disabled                                      |

An identity is matched by Google's subject id first, then by the verified address. When Google's verified address meets a password account whose address nobody proved, the password is removed and the account's sessions are ended, and the person keeps the account through Google: someone may have registered that address first and be waiting for its owner.

## E-mail

The API sends two mails over SMTP, always encrypted (`SMTP_*`, `MAIL_FROM`, `MAIL_REPLY_TO`): the verification link and the password reset link. They are Arabic, right to left, with a plain-text part. Check the settings from a server with `uv run python -m src.cli.mail_test you@example.com [--all]`.

- The link is `WEB_BASE_URL` (else `SITE_URL`) plus `/verify-email` or `/reset-password`, with the token after a `#` (`/reset-password#token=...`). A fragment is never sent to a server, so the token stays out of access logs. The page reads it from `location.hash` and posts it to the API; following the link by itself does nothing, so a mail scanner cannot spend it.
- A token is random, stored only as a hash, works once and expires (`EMAIL_VERIFICATION_EXPIRE_HOURS`, `PASSWORD_RESET_EXPIRE_MINUTES`). A new one cancels the earlier one. Tokens are never logged.
- While `SMTP_HOST` is empty nothing is sent: the routes answer as usual and the API logs `Cannot send ...: SMTP is not configured`. A failed send is logged the same way and never fails the request. The routes that mail a link answer 202 whether or not the address has an account, and send the mail after answering.

## An unverified address

An unverified account can sign in and use the app. It may not publish anything public: a route that does so depends on `VerifiedUser` (`src/deps.py`), which answers `403 EMAIL_NOT_VERIFIED`. On the social network (`docs/SOCIAL_NETWORK.md`) that is choosing a public handle and name, posting, commenting, following, liking and reporting; blocking, bookmarking, unfollowing and withdrawing one's own post need only a session. Putting a name on anything also needs a public identity (`PublicMember`, `409 PUBLIC_IDENTITY_REQUIRED`). The flag is `users.email_verified_at`, exposed to its owner as `email_verified` in `/auth/me`. It is set by following the verification link, by a completed password reset, or by Google, which verifies addresses itself.

## Behind nginx

Rate limits count the client address that uvicorn resolves from `X-Forwarded-For`, so the server must run with proxy headers on and trust only nginx (the defaults of uvicorn and gunicorn trust `127.0.0.1`). Without that, every client looks like `127.0.0.1` and shares one budget.

## Not built

Changing the display name, the e-mail address or the password while signed in; two-factor sign-in for ordinary accounts (the admin area has its own, with its own session: `docs/ADMIN.md`); a list of a person's own sessions with a way to end one; password re-entry before deleting an account.
