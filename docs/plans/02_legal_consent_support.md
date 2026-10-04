# 02 · Legal pages, consent and support

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-04 15:16 (Tunis)

Terms and privacy pages, the full-screen cookie choice, acceptance of the terms at sign-up, and a support form that e-mails `support@tabsira.me`.

| Step                                                                       | Status | Notes                                                      |
| -------------------------------------------------------------------------- | ------ | ---------------------------------------------------------- |
| Terms (/terms) and privacy (/privacy) pages in Arabic                      | ✅     | Drafted from the real data flows; need a lawyer's reading. |
| Full-screen cookie choice, shown from the first paint, page visible behind | ✅     | Works without JavaScript; proof kept on the server.        |
| Acceptance of terms and privacy at sign-up (e-mail and Google)             | ✅     | Server enforces it on every signed-in route.               |
| Asked again when the terms change                                          | ✅     |                                                            |
| Support form (/support) to `support@tabsira.me`                            | ✅     | Shared limits, nothing stored.                             |

**Waiting on the owners**

- Who publishes TABSIRA and under which law (owners).
- How long proof of consent is kept (owners).
- Lawyer's reading before launch.

**How we check it**

- Every promise in the privacy text matches the code (checked in review).
- Security review of acceptance and support: findings fixed.

## Tasks

### 02.1 Legal acceptance and support API: rebase and merge

- **Status:** ✅ 2026-10-04 15:16
- **Goal:** Server rules for accepting terms and privacy, the re-ask gate and the support form, after their security review.
- **Depends on:** —
- **Touches:** apps/api auth, legal, support, consents; one migration.
- **Done when:** Gate green; privacy review findings closed.

### 02.2 Consent proof retention job

- **Status:** ⏸ waiting on owners
- **Goal:** Delete proof of consent after the period the owners choose, in one scheduled job.
- **Depends on:** The owners' retention period.
- **Touches:** apps/api one CLI command, deploy/systemd one timer, docs/PRIVACY.md and the privacy page text.
- **Done when:** Rows older than the period are gone; the privacy page states the period.
