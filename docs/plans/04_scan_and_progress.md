# 04 · Photo to scan, with honest progress

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 17:35 (Tunis)

A person takes or uploads a photo. They see honest stages (understanding, searching, verifying, composing), can point at what matters and answer one question.

| Step                                                                             | Status | Notes                              |
| -------------------------------------------------------------------------------- | ------ | ---------------------------------- |
| Upload or link, size and safety checks                                           | ✅     | Built; merges after review.        |
| Queue with one worker, progress that resumes after a drop                        | ✅     | Built; merges after review.        |
| Photo shown only after the safety verdict; sensitive scenes never shown          | ✅     |                                    |
| Focus and one clarifying question                                                | ✅     |                                    |
| Rain tutorial, labelled as prepared                                              | ✅     |                                    |
| Production requires S3, checked at start; disk only in development (decision 44) | ✅     | Probe at boot and in check_config. |
| Scan worker unit, graceful restart, Redis persistence off                        | ✅     | Dry-run only; no server touched.   |
| Scripture review fixes, then merge                                               | 🔄     | In progress.                       |
| Screens: capture, progress, focus, question                                      | 🔄     | In progress.                       |

**How we check it**

- A live run end to end on `https://tabsira.test`.
- Scripture and privacy reviews passed.

## Tasks

### 04.1 Scan workflow: scripture fixes and merge

- **Status:** ✅ 2026-10-04 16:09
- **Goal:** Close the scripture review findings, then merge.
- **Depends on:** —
- **Touches:** apps/api scans, insights, world, me, tutorial.
- **Done when:** Scripture review passes; gate green.

### 04.2 Scan screens: capture, progress, focus, question

- **Status:** ✅ 2026-10-04 16:09
- **Goal:** Web screens for 04, built on the workflow API.
- **Depends on:** 04.1
- **Touches:** apps/web scan and insight components.
- **Done when:** Accessibility check clean; related tests pass.

### 04.3 Run the scan worker in production

- **Status:** ✅ 2026-10-04 15:13
- **Goal:** A systemd unit for the single scan worker, enabled by provisioning, restarted gracefully by the deploy; Redis persistence off for the scan database.
- **Depends on:** 04.1
- **Touches:** deploy/systemd/tabsira-worker.service, deploy/provision-app.sh, deploy/deploy.sh, deploy/provision-redis.sh, docs/OPERATIONS.md.
- **Done when:** `--dry-run` shows the worker steps; shellcheck and shfmt clean.

### 04.4 Tie chat answers to the texts shown when they were written

- **Status:** ⬜ open, after 04.1
- **Goal:** Each chat answer records the evidence ids shown when it was written; an answer whose texts are no longer all shown (a hadith since ruled out) is hidden or annotated and left out of the chat history sent to the model.
- **Depends on:** 04.1
- **Touches:** apps/api chat service and insight view, one migration.
- **Done when:** A test rules a cited hadith ineligible after a chat answer and the answer no longer shows or reaches the model; scripture review passes.

### 04.6 Catch short verses quoted whole

- **Status:** ✅ 2026-10-04 17:21
- **Goal:** Refuse model text that contains a whole stored verse of 3 to 6 guard words even without an introducer (for example «قل هو الله أحد» unmarked). Use a computed `guard_words` column with an index on `quran_verse_search` and a bounded check in `repeats_store` (padded guard text contains a short verse's padded `guard_text`); about 1,709 verses qualify.
- **Depends on:** 04.1
- **Touches:** apps/api scripture overlap and search models, one migration.
- **Done when:** Tests built from stored text (112:1, 94:6 added to the test extras from a `make data` store, bukhari 1) are refused in insights, chat and scene texts; the guard stays under 0.5 s per insight; scripture review passes.
- **Measured:** on the full store (6,236 verses, 65,712 hadiths), the whole store check of one insight's fifteen texts takes about 170 ms, the short-verse statement about 9 ms; 1,709 verses have three to six guard words.

### 04.7 Refresh the verse spans once per Quran sync

- **Status:** ✅ 2026-10-04 17:30
- **Goal:** `refresh_verse_spans` runs once at the end of a correction batch (end of `reconcile_verses`, after the loop in `quran_sync._apply_rows`), or `REFRESH MATERIALIZED VIEW CONCURRENTLY`, instead of once per corrected verse.
- **Depends on:** 04.1
- **Touches:** apps/api/src/scripture/quran.py, quran_sync.py.
- **Done when:** A test applies several corrections and the view is refreshed once and is correct.

### 04.8 Scan texts in the language catalogue

- **Status:** ✅ 2026-10-04 17:35
- **Goal:** Move the scan workflow's Arabic constants in `apps/api/src/messages.py` (about 32: the AI disclosure, labels, ranks, badges) into the per-language catalogue read through `messages_for()` (decision 36).
- **Depends on:** 04.1
- **Touches:** apps/api/src/messages.py and the modules that import those constants.
- **Done when:** No user-visible scan text is a module constant; tests pass.
