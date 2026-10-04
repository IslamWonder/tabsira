# 01 · Accounts and sign-in

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-04 14:51 (Tunis)

People can use TABSIRA as a guest, then create an account with e-mail or Google to keep what they saved. «ملفي» holds their account, answers, settings and data.

| Step                                                     | Status | Notes                                                                |
| -------------------------------------------------------- | ------ | -------------------------------------------------------------------- |
| E-mail sign-up, sign-in, verification and password reset | ✅     | Mails in Arabic.                                                     |
| Google sign-in                                           | ✅     | Needs the Google client from the owners to work outside development. |
| Guest use and merge at sign-in                           | 🔄     | Built with the scan workflow; merges with it.                        |
| «ملفي»: account, the three optional questions, settings  | ✅     | Theme is saved per device for now.                                   |
| Download my data, delete my account                      | ✅     |                                                                      |
| Sign-in limits that hold under parallel requests         | ✅     | From the security review.                                            |

**Waiting on the owners**

- SMTP account and Google client (owners).
- Guest merge lands with the scan workflow.

**How we check it**

- Sign up, verify, reset and delete on `https://tabsira.test`.
- 100 % tests; security review passed.

## Tasks

### 01.1 Save theme and motion settings to the account

- **Status:** 🔄 main machine
- **Goal:** Theme and motion follow the person across devices instead of staying per device.
- **Depends on:** —
- **Touches:** apps/api profile settings (schema, one migration), apps/web «ملفي» settings and the theme provider.
- **Done when:** Change it on one browser, see it on another after sign-in; guests keep the per-device choice; 100 % coverage.
