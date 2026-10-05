# 01 · Accounts and sign-in

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-04 14:51 (Tunis)

People can use TABSIRA as a guest, then create an account with e-mail or Google to keep what they saved. «ملفي» holds their account, answers, settings and data.

| Step                                                     | Status | Notes                                                                 |
| -------------------------------------------------------- | ------ | --------------------------------------------------------------------- |
| E-mail sign-up, sign-in, verification and password reset | ✅     | Mails in Arabic.                                                      |
| Google sign-in                                           | ✅     | Needs the Google client from the owners to work outside development.  |
| Guest use and merge at sign-in                           | ✅     | Every sign-in moves the guest's scans, insights, places and progress. |
| «ملفي»: account, the three optional questions, settings  | ✅     | Theme and motion follow the account; guests keep the device.          |
| Download my data, delete my account                      | ✅     |                                                                       |
| Sign-in limits that hold under parallel requests         | ✅     | From the security review.                                             |

**Waiting on the owners**

- SMTP account and Google client (owners).

**How we check it**

- Sign up, verify, reset and delete on `https://tabsira.test`.
- 100 % tests; security review passed.

## The mails TABSIRA sends

Three mails, all from `MAIL_FROM` through the `SMTP_*` server, in Arabic, text with an HTML alternative (`apps/api/src/templates/email/ar/`, `apps/api/src/services/email_service.py`). They go out after the answer (a background task), so their timing says nothing; a mail that cannot be sent is logged and never fails the request. Every link carries its one-time token after `#`, so it never reaches a server log.

| Mail                                                         | Subject                            | Sent when                                                                                                                                                                    | Not sent when                                                                                                                 | Link                                                                                                                       |
| ------------------------------------------------------------ | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Address verification, the welcome mail («أهلًا بك في تبصرة») | «أكّد بريدك الإلكتروني في تبصرة»   | Sign-up with an e-mail and a password (`POST /auth/signup`), at once; again on «أعد إرسال رابط التأكيد» (`POST /auth/resend-verification`) for an active, unverified account | A Google sign-up (Google has verified the address); an address already verified; no such account (the answer is the same 202) | `/verify-email#token=…`, 24 hours (`EMAIL_VERIFICATION_EXPIRE_HOURS`), once; a new one cancels the old                     |
| Password reset                                               | «إعادة تعيين كلمة المرور في تبصرة» | «نسيت كلمة المرور» (`POST /auth/forgot-password`) for an active account, Google-only ones included (they then gain a password)                                               | No such account or a closed one (the answer is the same 202)                                                                  | `/reset-password#token=…`, 60 minutes (`PASSWORD_RESET_EXPIRE_MINUTES`), once; resetting ends the account's other sessions |
| Support message, to the team                                 | «[تبصرة] <الموضوع>»                | The support form (`POST /support`), to `SUPPORT_EMAIL`, replies going to the visitor                                                                                         | —                                                                                                                             | none; plain text, the visitor's lines quoted                                                                               |

Not sent today: no mail when a password is changed, when the address is changed, when the account is deleted, and no newsletter of any kind.

Samples rendered from the templates (not sent) are in `../tabsira-artifact/mail-samples/`. To receive the real ones through production's SMTP: `cd /opt/tabsira/apps/api && UV_NO_SYNC=1 uv run python -m src.cli.mail_test you@example.com --all` (placeholder links).

## Tasks

### 01.1 Save theme and motion settings to the account

- **Status:** ✅ 2026-10-04 15:32
- **Goal:** Theme and motion follow the person across devices instead of staying per device.
- **Depends on:** —
- **Touches:** apps/api profile settings (schema, one migration), apps/web «ملفي» settings and the theme provider.
- **Done when:** Change it on one browser, see it on another after sign-in; guests keep the per-device choice; 100 % coverage.

### 01.2 Cloudflare Turnstile on the five abused forms: web

- **Status:** ✅ 2026-10-04 22:42
- **Goal:** Sign-up, sign-in, forgot password, resend verification and the support form show a Turnstile check when `TURNSTILE_SITE_KEY` is set on the web server, and send its token in the `CF-Turnstile-Response` header (decision 56).
- **Depends on:** The API side of decision 56 (verifies the token, answers 403 `turnstile_failed`), built in parallel against the same contract.
- **Touches:** apps/web (widget and hook, script loader on demand, server-env key, the five forms, messages, privacy text), docs/PRIVACY.md, `.env.example`.
- **Done when:** Key empty: nothing rendered or loaded, no header. Key set: the script loads once on those pages only, the header is attached, the widget resets after every submit, a 403 `turnstile_failed` shows an Arabic message; a blocked script shows its own Arabic notice (allow challenges.cloudflare.com or try another browser), and since the API refuses a form without a token it fails closed. The «ملفي» resend button became a link to `/verify-email`, where the check lives. Vitest at 100 % for the new code.
