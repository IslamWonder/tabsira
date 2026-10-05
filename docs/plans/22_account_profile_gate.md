# 22 · Account after the first scan, full profile, fitted answers

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-05 (Tunis)

Decision 64: a visitor gets the rain tutorial and one own scan; then an account, a completed profile, and AI answers fitted to it. The real full name is public only with its own consent.

| Step                                                      | Status | Notes                  |
| --------------------------------------------------------- | ------ | ---------------------- |
| Guest gate and profile gate on the server                 | ✅     | Task 22.1, 2026-10-05. |
| Full-name consent and public name                         | ✅     | Task 22.1, 2026-10-05. |
| Profile in the composer and the chat prompts              | ✅     | Task 22.2, 2026-10-05. |
| Screens: sign-up, mandatory profile step, no guest button | ✅     | Task 22.3, 2026-10-05. |

**How we check it**

- A guest key holding one own scan gets 403 `account_required` on a second `POST /scans`; the rain tutorial never counts (tested).
- An account with `profile_completed_at` empty gets 403 `profile_required` on `POST /scans` and the chat (tested).
- A post and a public profile carry the full name only while the `public_full_name` consent is given; withdrawn, only the handle (tested).
- With personalization off the composer and the chat receive no profile field; with every field `unknown` the prompt payload equals today's (tested).
- No scripture text in any new prompt; the scripture guards unchanged (scripture review).

## Tasks

### 22.1 Gates and the full-name consent, server side

- **Status:** ✅ 2026-10-05
- **What was done:** `POST /scans` answers 403 `account_required` for a guest key holding one non-failed scan (the tutorial never counts) and 403 `profile_required` for an account with empty `profiles.profile_completed_at`; the insight chat answers `profile_required` after the ownership check. `PATCH /profile` takes `complete_profile: true` with all five answers explicit; `/auth/me` carries `profile_completed` and `public_full_name`. New consent kind `public_full_name` (sign-up body, `POST /auth/legal/accept` for Google, `POST /consents`), mirrored on `users.public_full_name`; every public answer carries `public_name` (the real full name) only while it is true, else null. Not backfilled: existing accounts are asked once. Privacy review fixes: under 13 never shows the full name; withdrawing passes the legal gate; takeover (Google, reset) withdraws the consent and resets the name; names are checked and never fall back to the e-mail address; focus and clarify are gated; the guest count is taken under a lock; an unticked box is a refusal row. `users.public_name` is no longer read (not emptied). Terms and privacy bumped to `2026-10-05T18:00Z`. The web client types were regenerated; the screens that read `public_name` as a string and the sign-up body no longer type-check until 22.3.
- **Production `.env`:** no new key. `TERMS_VERSION` and `PRIVACY_VERSION` change to `2026-10-05T18:00Z` in `.env.example` and `deploy/env.production.example`; the owners set the same values in production (the checklist does not check them); every account is asked to accept again.
- **Touches:** apps/api/src/{models/profile.py,models/user.py,schemas/auth.py,schemas/account.py,schemas/social.py,services/public_identity.py,services/learner_service.py,routers/scans.py,routers/auth*.py,services/chat_service.py (the gate only)}, one app-chain migration, the terms and privacy text, docs/PRIVACY.md, docs/AUTH.md, the generated OpenAPI.
- **Reviews:** privacy review before merge (authentication, public identity); tests in the same commit (decision 42 exception).

### 22.2 Profile-fitted composer and chat

- **Status:** ✅ 2026-10-05
- **Touches:** apps/api/src/pipeline/{insight/composer.py,prompts/insight_composer_system.v5.txt,prompts/insight_chat_system.v6.txt}, apps/api/src/services/chat_service.py (the learner payload), docs/plans/20_prompts.md.
- **Reviews:** scripture review before merge (prompts).
- **Done:** `LearnerContext.gender`; `learner_view()` feeds the composer (`insight_composer_system.v5`, never the gender, one neutral publishable text) and, with a declared gender, the private chat (`insight_chat_system.v6`, `$learner`); `learner_service.profile_context()` gives the chat the declared fields without the history. Tests in `tests/insight/test_stages.py`, `tests/scans/test_learner.py`, `tests/scans/test_chat.py`. `make eval` not run (no provider key on the machine that built it): the new prompts are not yet measured on the gold scenes and chat cases.

### 22.3 Screens

- **Status:** ✅ 2026-10-05
- **Depends on:** 22.1 (OpenAPI).
- **Touches:** apps/web/src/{components/insight/completion-panel.tsx,components/account,components/me/settings-section.tsx,app/scan,app/signup,messages/ar.ts,lib/api}.
- **Done when:** after the first own scan the save invitation has no guest button; a new account lands on the full profile form before anything else; each field offers «أفضّل عدم الإجابة»; the sign-up form shows the unticked full-name box; posts show the full name only when the API sends it.
- **Done:** sign-up asks the real full name and has its own unticked full-name box (also in the legal gate and carried through the Google tick); `/me` public identity takes the handle only and has the full-name switch; every public name shows the handle alone when `public_name` is null; guest sees no «أتابع كضيف», a second scan or the chat of an own scan goes to `/signup?next=…&reason=scan|chat`; `ProfileGate` (full-screen, after the terms gate) asks the five answers with «أفضّل عدم الإجابة» and opens on `profile_completed: false` or a 403 `profile_required`. Retired: the optional first-insight questions (`FirstInsightQuestions`, `ProfileQuestions`). Left in place, now unused by the journey: `PROFILE_QUESTIONS_MAX`, the device answers hand-over.
