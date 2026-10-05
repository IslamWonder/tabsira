# 04 · Photo to scan, with honest progress

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 20:55 (Tunis)

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
| Chat answers tied to the texts shown when written                                | ✅     | Hidden once a text is not shown.   |
| Optional questions after the first insight, share option after saving, §8 labels | ✅     | Core audit wave 3, task 04.11.     |
| Chat request for another text re-runs retrieval and verification                 | ✅     | Found text read from the store.    |
| Found text shown under the chat answer, with the insight's evidence cards        | ✅     | Task 04.15.                        |

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

- **Status:** ✅ 2026-10-04 17:37
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
- **Measured:** on the full store (6,236 verses, 65,712 hadiths), the whole store check of one insight's fifteen texts takes 170 to 290 ms (idle machine to one shared with other test runs), the short-verse statement 9 to 12 ms; 1,709 verses have three to six guard words.

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

### 04.9 Fold the joined vocative the way today's spelling writes it

- **Status:** ⬜ open
- **Goal:** The mushaf joins «يا» to the word after it; today's spelling writes it apart, which changes the word count and the word boundaries, so 17 of the 20 short verses with a joined vocative (20:11, 20:17, 20:19, 20:36, 20:49, 20:95, 21:14, 21:62, 25:28, 27:9, 37:20, 37:104, 68:31, 69:27, 71:2, 89:24, 109:1) escape the whole-verse check of 04.6 when written as today, and `tests/scripture/spelling.py` keeps the joined form, so the spelling sweep overstates what it covers (found by the scripture review of 04.6). Join a lone skeleton word «ي» (and «ه») to the next word in `guard_fold`, on both sides, and make the spelling helper split the vocative as today's spelling does.
- **Depends on:** 04.6
- **Touches:** apps/api/src/scripture/guard_fold.py, tests/scripture/spelling.py, tests/scans/test_spelling_guard.py.
- **Done when:** 109:1 in today's spelling, built from the stored text, is refused in insights, chat and scene texts; the sweep passes with the split vocative; scripture review passes.

### 04.10 Drop invisible characters and presentation forms before the guard fold

- **Status:** ⬜ open
- **Goal:** A soft hyphen (U+00AD), a word joiner (U+2060 to U+2064), U+034F or a variation selector (U+FE00 to U+FE0F) inside a word splits it without showing, and the Arabic presentation forms (U+FB50 to U+FDFF, U+FE70 to U+FEFF) are other code points for the same letters, so a text written with them passes both store checks (found by the scripture review of 04.6). Add a pre-pass to `guard_fold` only, never to `search_copy` or the stored text, that removes the invisible characters and maps presentation forms to their letters.
- **Depends on:** 04.6
- **Touches:** apps/api/src/scripture/guard_fold.py, tests/scripture/test_guard_fold.py, tests/scans/test_spelling_guard.py.
- **Done when:** Tests built from stored text with these characters inserted are refused by `repeats_store`; scripture review passes.

### 04.11 Core audit wave 3: the journey after the first insight

- **Status:** ✅ 2026-10-04 20:37
- **Goal:** Close four gaps of the wave 3 compliance audit against master prompt v2. (1) The three optional questions (§5, §4.7, §4.9) are offered in the journey after «تمّ» on a first insight, one at a time, each with «تخطَّ» and «تخطَّ الأسئلة كلها»; skipping keeps every field `unknown`. A guest is asked on a first insight only; an account is asked after any insight until it has been asked once, so an account created after its first insights still gets them. An account records that they were asked (`profiles.questions_asked`, migration `20261004_205000`; `PATCH /profile` sets it on any answer, on a skip to `unknown`, or on `{"questions_asked": true}` alone) and is never asked again; a guest keeps the answers and the flag on the device (`tabsira.profile-answers`) and the first sign-in moves them into the account. (2) `PROFILE_QUESTIONS_MAX` (0 to 3) is a typed API setting, listed in `.env.example`, read by the web build from the shared `.env` and inlined as `NEXT_PUBLIC_PROFILE_QUESTIONS_MAX`. (3) After saving, the third option «شارك البصيرة» (§4.8) is rendered under the API's label when the API lists it and the owner may publish; otherwise one line says why (sign in to share; a prepared example is not shared; not available). (4) The refusal (§8) offers «وضّح ما تقصد» and «جرّب مشهدًا آخر».
- **Depends on:** 04.2, 05.1
- **Touches:** apps/api/src/{config.py,models/profile.py,schemas/profile.py,services/profile_service.py}, one app migration, apps/web/src/{account/device-answers.ts,components/account/first-insight-questions.tsx,components/insight/completion-panel.tsx,components/insight/insight-screen.tsx,config/public-env.ts,lib/site.ts,messages/scan.ts,messages/legal.ts,preferences/account-sync.ts}, .env.example, the generated web client, their tests.
- **Done when:** Lint passes; the profile, config, migration and the touched web tests pass; a guest and an account are each asked once and never again.
- **Numbering:** the audit named this task 04.10; 04.10 was already taken by the guard fold follow-up above, so it is 04.11 here and the branch kept its name `task/04.10-core-audit-web`.

### 04.12 Draw a box to point at what matters

- **Status:** ⬜ open
- **Goal:** Master prompt v2 §6 resolves an ambiguity with one short question **or a manual selection of the place in the photo**; the API already accepts `FocusIn.box` (ratios 0 to 1), but the web focus picker (`apps/web/src/components/scan/focus-picker.tsx`) offers the server's entities only (audit wave 3, gap 8). Add a draw-a-box mode to the picker: a touch or pointer drag on the photo draws one rectangle, clamped to the image, shown with the same glass label; «انظر إلى هذا» calls `focus` with `box` instead of an entity id; a keyboard path moves and resizes the box with the arrow keys from a real `<button>`; the mode is offered when the picker has no entities («لم نتعرف على شيء يمكن اختياره هنا») and beside the list when it has some. No hover motion; reduced motion respected; targets at least 48 px.
- **Depends on:** 04.2
- **Touches:** apps/web/src/components/scan/focus-picker.tsx, apps/web/src/lib/scan/use-scan.ts, apps/web/src/messages/scan.ts, their tests.
- **Done when:** A test draws a box and the request carries `box` with ratios inside 0 to 1 and no entity id; the picker with no entities offers the box; accessibility check clean.

### 04.13 Core audit (wave 3): the four API gaps

- **Status:** ✅ 2026-10-04 20:42
- **Goal:** Close the four API gaps of the wave 3 compliance audit of the core journey (report beside the checkout, `reviews/audit-wave3-core-2026-10-04.md`). (1) The composer's neutral-explanation rule keyed on a background the payload never sends (`exploring`/`other`); the prompt now rules on `muslim`, `non_muslim`, `unknown` or absent, the payload keeps the profile enum, and a non-Muslim or unshared background gets the «يعلّم الإسلام» framing (v2 §5). (2) An account that declared it is under 13 cannot publish an insight at all, not only its photo: `409 UNDER_13_CANNOT_PUBLISH`, named in the share sheet, the privacy policy and the terms (v2 §5). (3) `EvidenceExposure` records what was shown when it is shown: a `shown` row the first time each text of an insight reaches its owner (`GET /insights/{id}`, a kept tutorial insight), once per insight and text, unless memory is off; the engine's «seen» diversity reads it (v2 §11, masar §10.5). (4) A server-side guard replaces any word that names a person by religion, age or gender in the scene's labels and texts with «شخص» and records it in `rejected` (v2 §0.6, §6; `src/pipeline/person_words.py`).
- **Depends on:** 04.1, 09.1
- **Touches:** apps/api/src/pipeline/{prompts/insight_composer_system.v1.txt,insight/planner.py,scene_analyzer.py,person_words.py}, apps/api/src/services/{public_insight_service.py,insight_view.py,learner_service.py,completion_service.py,world_service.py}, apps/api/src/routers/{insights.py,tutorial.py}, apps/api/src/errors.py, apps/api/src/models/timeseries.py, their tests, apps/web/src/components/insight/share-sheet.tsx, apps/web/src/messages/{share.ts,legal.ts}, the generated web client, docs/PRIVACY.md.
- **Done when:** The tests of each fix pass; `make lint` passes. Not done here: posts and atlas entries of an under-13 account still answer `INSIGHT_NOT_PUBLISHABLE` only for the photo (posts) or the location (atlas); the owners decide whether §5 closes those too.

### 04.14 A chat request for another text re-runs the retrieval and the verification

- **Status:** ✅ 2026-10-04 20:55
- **Goal:** v2 §14 («طلب نص إضافي يعيد الاسترجاع والتحقق؛ لا جواب من الذاكرة»): when the chat model classifies a message as a request for a verse or a hadith that is not shown, the app runs a focused retrieval for it instead of the fixed message alone. One candidate is built from the insight's concept and the learner's words (no planner call), searched through the engine's hybrid search with the scan's reranker setting, the insight's own texts left out, judged by the verifier against the scan's stored scene and gated by the same rules (a hadith an editor ruled out is never shown; any other is shown as stored, decision 64). A text that passes is named by reference in the app's own words and attached to the chat message as an evidence id, so the insight page reads it from the store byte for byte beside the answer and withdraws the answer once the text is no longer eligible; when nothing passes, the honest message stays. The model never writes scripture; every text shown meets the leak guard. The three-message limit and the idempotency key are unchanged. Cost: one embedding call and one verifier call.
- **Depends on:** 04.4, 05.1
- **Touches:** apps/api/src/services/{chat_service,chat_retrieval,insight_view}.py, routers/insights.py, schemas/insight.py (`ChatMessageOut.quran`, `ChatMessageOut.hadith`), messages.py, prompts/insight_chat_system.v4.txt, evaluation/chat_eval.py (an optional `scene` per case insight), tests/scans/test_chat.py, tests/insight/test_chat_cases.py, tests/evaluation/chat/cases.json, the generated web client.
- **Done when:** A test asks for another text on an insight with a scene and gets the found verse from the store with its hash, a found hadith without a ruling is queued and not shown, a ruled-out found hadith withdraws the answer, and the twelve cases accept `answer` or `new_search` for the new-text case; scripture review passes. Not done here: the web shows `quran` and `hadith` on a chat message (a follow-up for the web).

### 04.15 Show the text a chat answer found, beside the answer

- **Status:** ✅ 2026-10-04 21:08
- **Goal:** Follow-up of 04.14 for the web (v2 §14): when a chat message carries `quran` or `hadith`, the insight screen shows that text under the answer with the same evidence cards as the insight (`InsightEvidence`, so `EvidenceCard` stays the only rendering of scripture): the store's text byte for byte, the fixed tags «القرآن» and «السنة», the reference, the quranpedia link, the ruling and the «تحقق في الدرر» link, and the verified chip when the API matched the text to its hash. The cards take heading level 3 under the sheet's own title. A message without texts renders as before; nothing else about the chat changes.
- **Depends on:** 04.14
- **Touches:** apps/web/src/components/insight/{chat-sheet.tsx,insight-evidence.tsx} (an optional `headingLevel`) and their tests.
- **Done when:** A test renders a message with both texts and compares what is shown byte for byte with the API's text and with its stored hash; one text alone shows one card without a notice; a message without texts shows no card. `make lint` passes.

**How we check it**

- A live run end to end on `https://tabsira.test`.
- Scripture and privacy reviews passed.

### 04.16 Rate an insight: useful or not, why, and a note

- **Status:** 🔄 2026-10-05: the API is on `main`; the web prompt follows.
- **Goal:** a discreet way for the reader to say whether an insight was useful, at the end of the experience and from a small menu at any time. «Not useful» takes reasons from a fixed list (`wrong_text`, `misread_scene`, `wrong_explanation`, `offensive`, `other`) and an optional note of 300 characters. One rating per insight, changed in place; a changed rating goes back to the team's review queue.
- **API:** `PUT /insights/{id}/feedback` (the insight's owner, guest or account), the rating in `GET /insights/{id}` (`feedback`), `learning.feedback` in `GET /account/export`, table `app.insight_feedback` (migration `20261005_190000`, deleted with the insight), admin view «Insight ratings» (read-only, «Mark reviewed»).
- **Privacy:** the privacy page (version 2026-10-05T20:00Z) and `docs/PRIVACY.md` say what is kept and who reads it.
- **Production `.env`:** no new key. `PRIVACY_VERSION`, if the file sets it, must become `2026-10-05T20:00Z` (or be removed so the code's value applies); the checklist compares it with the example.
