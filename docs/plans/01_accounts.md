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
