# Challenge log

The work of the challenge days on TABSIRA. The 4 October section is built from `git log --date=format:'%H:%M' --format='%ad %s' main` for 4 October 2026 (times are Tunis time, the committers' clock, UTC+1). The log held 634 entries; 568 distinct subjects remain once the commits that two merged branches carried twice are counted once. Every line of the log is one commit, one logical change; the subjects are the detail, this file is the shape of the day and what it did not finish.

Two sources say where things stand: `docs/plans/README.md` (the features and their tasks, with the time each one was marked done) and `docs/spec/DECISIONS.md` (54 decisions, 51 to 54 taken today). Nothing here is a claim beyond those two files.

## Starting point

The participant's guide (`docs/spec/contest-guide.md`) allows a project started before the challenge when its starting version is documented; only the work of 4 to 6 October is judged. This repository's first commit is `docs: add rules for AI coding agents`, on 4 October 2026 at 07:44 Tunis time: every line of code, test, script and document here was written during the challenge days (769 commits on 4 October, 273 on 5 October, and those of 6 October). What came from before, and is named where it is used:

- **The earlier prototype** of this product (the owners' own): its look (the eight-point star mark, the aurora backdrop, the light motes, StageOrbit and QuestLog, `docs/DESIGN_DECISION.md`), its gamification rules (decision 27), the Turnstile choice (decision 56) and one test photo (`child-cat.jpg`, provenance in `apps/api/tests/evaluation/scenes/gold.json`). No code was copied from it.
- **Data prepared before the challenge by the authors:** the annotated Quran corpus (`final_complete_verses_20251202_194512.json`, 2 December 2025), the enriched Sunnah file, the world ontology and the learning path «مسار» (`docs/SOURCES-AND-LICENSES.md`, «Retrieval aids»).

## 4 October, hour by hour

| Hour  | api | web | docs | admin | data | vision | tooling | Total |
| ----- | --- | --- | ---- | ----- | ---- | ------ | ------- | ----- |
| 07:00 | 0   | 0   | 3    | 0     | 0    | 0      | 1       | 4     |
| 08:00 | 8   | 0   | 10   | 0     | 5    | 4      | 9       | 36    |
| 09:00 | 19  | 0   | 10   | 0     | 30   | 0      | 9       | 68    |
| 10:00 | 20  | 14  | 9    | 8     | 7    | 0      | 3       | 61    |
| 11:00 | 25  | 1   | 5    | 5     | 0    | 0      | 3       | 39    |
| 12:00 | 33  | 4   | 5    | 3     | 0    | 1      | 9       | 55    |
| 13:00 | 47  | 14  | 4    | 1     | 0    | 0      | 1       | 67    |
| 14:00 | 18  | 15  | 10   | 0     | 0    | 0      | 7       | 50    |
| 15:00 | 15  | 10  | 18   | 0     | 0    | 0      | 3       | 46    |
| 16:00 | 12  | 6   | 14   | 0     | 0    | 0      | 4       | 36    |
| 17:00 | 15  | 8   | 7    | 0     | 0    | 0      | 6       | 36    |
| 18:00 | 18  | 7   | 7    | 0     | 0    | 0      | 3       | 35    |
| 19:00 | 6   | 7   | 5    | 0     | 0    | 0      | 9       | 27    |
| 20:00 | 0   | 2   | 3    | 0     | 0    | 0      | 3       | 8     |
| All   | 236 | 88  | 110  | 17    | 42   | 5      | 70      | 568   |

Areas are the commit prefixes: `data` gathers `scripture`, `ontology`, `learning`, `geo`, `geodata` and `data`; `tooling` gathers `deploy`, `nginx`, `ci`, `scripts`, `chore`, `env`, `brand` and the one merge commit.

**07:00–08:00 — rules and foundations.** The rules for coding agents (`AGENTS.md`), the project subagents, the governing specs and the first decisions (TimescaleDB, the admin area, the nine PostgreSQL extensions). Three design directions were proposed and the owners chose: a night structure with a light theme in day colours. Then the skeleton: the uv project, typed settings, the two Alembic chains, the health route, the Makefile whose stubs fail honestly, formatting and linting, nginx for `tabsira.test`, the detector service with its AGPL licence, and the decisions on quranpedia text, the nine hadith books and dorar.net grading.

**09:00 — scripture, geography and the learning path.** The hour with the most data work: the scripture tables with hashed text and a write guard, quranpedia Hafs text imported with per-verse hashes and verified dumps, the daily corrections feed, the nine books, the annotated corpus for retrieval only, dorar rulings recorded by hand with a verification queue, and `/scripture` read-only. GeoNames with folded Arabic search names, tiered prefix search and the privacy grid. The world ontology workbook and «مسار» parsed into versioned data. Accounts: password, Google and e-mail sign-in, sessions, rate limits, transactional mail. The Jenkinsfile with SonarQube and per-build PostgreSQL and Redis.

**10:00 — the first interface and the admin area.** The Next.js app with strict types and coverage gates, the responsive shell, theme tokens with measured contrast, self-hosted fonts including KFGQPC Uthmanic Hafs, the rain scene with glowing points, evidence cards that render scripture exactly as stored, game-feel effects that respect reduced motion, the typed API client and the PWA manifest. The vision benchmark ran and set the provider defaults (OpenAI by default, OVH switchable). The admin area began: sqladmin with its own sign-in, the TOTP second factor, twelve-hour sessions, the append-only audit log as a hypertable.

**11:00 — consent, errors, photos, sitemap.** Cookie consent recorded at `/consent`, browser error reports at `/client-errors` forwarded to GlitchTip only when configured, the S3 and local photo stores with EXIF read first and stripped on re-encode, the refusal to keep a photo of a guest, an under-13 or a sensitive scene, the dynamic sitemap, IndexNow for production. The scan workflow's tables, settings, error codes and Arabic messages; guest identities and the owner of each request; the SSRF guard on photo addresses; the Redis job queue with one worker and a replayable progress stream. The logo and its two golds. The social network tables and the text moderation call.

**12:00 — deployment written, scans wired, social and retrieval begun.** The whole of `deploy/`: data host and application host provisioning, the atomic release deploy with rolling API and web restarts, pm2, gunicorn, systemd, logrotate, sudoers, the VPN-only admin host and the shared nginx header snippets, the opt-in Jenkins deploy stage. Scan routes (upload or address, progress, focus, clarify), insights served from the store with chat, step and completion, the world routes and practice progress, the rain tutorial served from the store and labelled prepared, public ids, the scan worker as its own process, photos sealed in Redis with a key Redis never holds. The legal pages and their Arabic texts. Public handles, profiles, follows and blocks. Scripture embedded resumably, hybrid search fused by RRF, a cross-encoder reranker in the vision service.

**13:00 — the insight engine and the guards.** The busiest hour of the API: the engine contract (plan, search, gate, compose), `make eval` on the gold scenes, the retrieval benchmark, the store-wide quotation check on trigram indexes that finds quotations running across short verses, the chat guarded against every text the insight cites, a step labelled from the sunnah only when its hadith grounds it, limits per address, the guest merged at sign-in. The account screens: sign-in, sign-up, mailed links, the terms gate, the profile page, cookie consent in the first paint, the accessibility check with axe. Admin hardening: sign-in attempts recorded before the password is checked, sessions ended on a credential change, `/admin` on its own host.

**14:00 — the scan and insight screens, the reranker, the personal world.** The web scan screen with progress, focus, clarification and results; the insight screen with sources, why-sheet, step, chat and completion; real scans started from the scene and the rain insights opened from the API; the personal world as a fog map with places, threads and treasures; «تمرينك» with ranks, streak, quest, sky of meanings and badges. The reranker on the eight best candidates with a timeout, the engine evaluation recorded, the core-first scope of the release recorded, one test worker per agent and one gate at a time.

**15:00 — reviews and the admin queues.** The rulings queue and the moderation queue in the admin area with their scripture and security reviews; S3 required in production with the bucket proved at start; the scan worker under systemd; the quotation guards extended to today's spelling and to any quotation after a scripture introducer; the chat answered by the insight stages' model; the postpone button renamed «سأفعله لاحقًا»; TABSIRA recorded as free; the phase-mode testing rule (decision 42); the axe check in Jenkins; `make stats`.

**16:00 — vectors in their own schema, the engine in the workflow.** The scripture vectors moved to a `vectors` schema with a third Alembic chain, exported and imported as one verified archive, the insight engine run as the scan workflow's engine with every stage behind the shared guard and the whole store; setting up a machine without importing anything twice; the social screens (feeds, posts, comments, profiles, publishing) and the atlas API placing insights at approximate points, both after their privacy and scripture reviews; the moderation queue extended to map entries.

**17:00 — publication, deploy rehearsal, atlas screens.** Publish and withdraw an insight and read it publicly, the public insight page, the share card drawn at `/insights/{id}/card` from TrueType faces kept in the repository, the share sheet; the deploy rehearsed in two containers standing in for the two hosts, with the gaps it showed fixed (backup as root, restore as the superuser, Redis password out of the URL, nginx started when found stopped); the atlas map, entry and place pages; the twelve chat cases asked by `make eval` and checked by rule; the verse spans rebuilt once per import.

**18:00 — quality tuning and plain HTTP locally.** Task 05.3: moderation beside the scene analysis, one verifier and one composer call per item run together, refinement only when nothing holds, a general reminder only when nothing stronger holds, no reranking call by default (decision 50): p50 from 26.7 s to about 18 s and the cost per scan from $0.0204 to about $0.016, recorded in `docs/EVALUATION.md`. Local development over plain HTTP on port 80 (decision 49) with cookies without the Secure flag only there. Chat answers refused when the shown texts changed while they were written.

**19:00–20:00 — atlas fixes, camera discovery, the capture flow, the audit.** The atlas after its reviews: no cached atlas answers, publication dated to the day, tombstones kept, 204 on blocking an unheld handle. Camera discovery over the atlas by place and direction, with a note instead of a crash when WebGL2 is missing. The scan started from a live camera or a photo, never a pasted link (decision 51). `make data` importing the store, the vectors and GeoNames once. Stale branches closed. The production template listing every API setting, the corpus read from a shared folder, nginx, PostgreSQL and Redis allowed to start before the VPN address exists. The compliance audit of the day recorded decisions 52 to 54 (guest insights on the server, the card without a photo, `FEATURE_PUBLIC_PAGES` realised by `FEATURE_SOCIAL`).

## 5 October, by theme

273 commits (`git log --since=2026-10-05 --until=2026-10-06 main`), the same rules: one commit, one change.

- **The search path rebuilt (task 05.8).** Intents planned from the scene, the enriched Sunnah file searched first and the store after, a relevance verifier that tests rather than justifies, verses judged with their neighbours, prompts with no worked examples and no scripture; the prompt inventory in plan 20.
- **Hadith display (decisions 64 and 65).** A hadith the gate accepts is shown as stored, with no ruling displayed; a hadith an editor ruled out stays hidden.
- **Accounts and profile (decision 63, plan 22).** An account after the first scan, a mandatory profile, the real full name shown only by its own consent, under-13 rules; the composer and the chat fit the declared profile without revealing it.
- **Photos.** A private folder per account, emptied with the account; the published photo on a public insight.
- **The social network and the atlas switched on.** One feature switchboard (`DISABLED_FEATURES`, `ENABLED_FEATURES`), comments off by default, the two reactions «انتفعت بها» and «جزاك الله خيرًا», orphaned atlas entries and their sponsoring (decision 60), clusters and a paged list on the atlas, following from a post, a country by consent, profile sharing.
- **Mock members (decision 66, plan 23).** A generator, the real pipeline run over placepix photos, an importer and its clean, complete members with every feature.
- **Interface.** The landing page with its opening scene, the world under clouds, the sky of meanings, the sources page, insight sounds, ratings of an insight, map controls, the type scale.
- **Delivery.** The AGPL-3.0 licence, GitHub Actions and the Jenkins deploy job, macOS and Windows setup scripts, a production check that refuses a file missing a key, the fourth coverage pass (task 15.3).

## 6 October, by theme

- **Contest documents.** The reference pack and the participant's guide summarised with their open points (`docs/spec/contest-reference.md`, `docs/spec/contest-guide.md`); the tools used registered beside the sources.
- **The leak guard in today's spelling (task 05.9).** Our own converter writes the stored quranpedia verses in today's spelling for the guard only; the 18 short verses with a joined «يا» that escaped are now refused, and 5-word quotations in today's spelling missed fell from 1,231 runs to 125 (measured against an outside text kept out of the repository). Two scripture reviews passed.
- **A campfire is not violence.** The scene prompt v4 names what is not violence; two campfire photos measured before and after, the gold sensitive scene still caught.
- **Mock data audited and corrected.** A scripture review of every mock photo's hadith link, the wrong ones run again through the pipeline, re-audited, and the rest withdrawn; the file patched without regenerating it, and a command that rewrites the imported rows in place (`import_mock --refresh-insights`), rehearsed on a copy of the production state.
- **Post views, reading aids, the speaker while a sound plays**, fixes to the practice page, the sky, the chat's account prompt; a static-analysis pass (SonarQube) over the API and the web.
- **Evaluation.** `make eval` with the new guard: 13 of 15 gold scenes as expected (10 of 15 that morning), no leak, every reference resolved, the twelve chat cases 12 of 12.

## Done and open

From `docs/plans/README.md` on the evening of 4 October; the plans index holds the current state.

| Feature                                    | Status       | What is open                                                                                                                                                                                        |
| ------------------------------------------ | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 01 Accounts, 02 Legal, 03 Scripture        | ✅           | 02.2 consent proof retention and 03.1 the rain-scene hadith rulings wait on the owners (an editor records them in the admin rulings queue or by `python -m src.cli.record_ruling`).                 |
| 04 Photo to scan                           | 🔄           | 04.9 (the joined vocative in the guard fold) and 04.10 (invisible characters before the fold) are open and were taken this evening.                                                                 |
| 05 Insight engine                          | 🔄           | 05.5 verify the uploaded archive when needed; 05.7 judge and write in one call per candidate (about 12 s a scan needs one call fewer). The rebased engine was not re-run end to end by `make eval`. |
| 06, 07, 08 Insight screen, world, practice | ✅ tasks     | The feature files still read 🔄 pending the phase-1 test task.                                                                                                                                      |
| 09 Share card and public page              | ✅ tasks     | Share-card byte size is not asserted in a test; the share sheet has no «تنزيل» button (audit of 4 October).                                                                                         |
| 10 Design, 11 Analytics and SEO, 12 Admin  | ✅           |                                                                                                                                                                                                     |
| 13 Reviews                                 | 🔄           | 13.1 the final review before release, after phase 1 merges.                                                                                                                                         |
| 14 Deployment                              | 🔄           | Rehearsed in containers; no real server has been touched. 14.1 real hosts, 14.2 copying backups off the data host wait on the owners.                                                               |
| 15 Quality gates                           | 🔄           | 15.3 back to 100 % coverage (web last at 99.93 %), taken this evening; 15.4 `make bootstrap`; 15.2 the history rewrite, on the main machine at the end of the phase.                                |
| 16 Social, 17 Atlas, 18 Camera             | 🔄 / ✅ / 🔄 | Phase 2. Camera discovery is built but not tested on a real phone.                                                                                                                                  |

Not built, from the audit of 4 October: the developer panel `/dev/inspect/{scanId}` (the trace is stored, no route renders it), a skip path that keeps a profile answer `unknown` without re-asking, a Docker compose file (decision 20 ruled Docker out of deployment; `make up` fails on purpose).

## Delivery table (v2 §30)

As written on 4 October; the contest's own list and where each item stands now are in `docs/spec/contest-guide.md`.

| Deliverable                    | Where                                                                                                                                                                     | Standing                                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| The live link                  | `https://tabsira.me`                                                                                                                                                      | Not deployed yet: the deploy is written and rehearsed in containers, the hosts are the owners'. |
| Main green in Jenkins          | `Jenkinsfile`, `jenkins/`, `docs/JENKINS_SETUP.md`                                                                                                                        | Pipeline written; no Jenkins instance has run it (the owners supply the server).                |
| A line per change              | `git log main` (one line per commit) and this file                                                                                                                        | Done.                                                                                           |
| Public repository              | The owners' remote                                                                                                                                                        | Local `main`; the owners push and publish.                                                      |
| `README` with two run modes    | `README.md`                                                                                                                                                               | Done. There is no demo account: the rain scene needs none, and a guest cookie covers the rest.  |
| `docs/SOURCES-AND-LICENSES.md` | `docs/SOURCES-AND-LICENSES.md`                                                                                                                                            | Done.                                                                                           |
| `docs/BENCHMARK.md`            | `docs/BENCHMARK.md`                                                                                                                                                       | Done, written by `make benchmark`.                                                              |
| `docs/EVALUATION-REPORT.md`    | `docs/EVALUATION.md` **is the evaluation report**, written by `make eval`: gold scenes, the twelve chat cases, time and cost per scan. No file by the spec's name exists. | Done under its own name.                                                                        |
| `docs/OPERATIONS.md`           | `docs/OPERATIONS.md`                                                                                                                                                      | Done, with the cost, alternatives and content-review section.                                   |
| The presentation deck          | Not in the repository.                                                                                                                                                    | Not made.                                                                                       |
| The video                      | Not in the repository.                                                                                                                                                    | Not made.                                                                                       |

**What is what**, as §30 asks (منفَّذ حي / محتوى مُعدّ موثَّق / محاكاة معلنة / مؤجَّل):

| Kind                               | What                                                                                                                                                                                                                                                                                                                   |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Live (منفَّذ حي)                   | The scan pipeline with the real providers (`SCAN_ENGINE=pipeline`), the scripture store and its guards, accounts and guests, the personal world and practice, publication and the share card, the social network and the atlas behind their feature flags, the admin area, the evaluation and benchmark commands.      |
| Prepared, documented content       | The rain scene («مثال موثّق مُعدّ», `GET /tutorial/rain`, `data/tutorial/rain-1.0.json`): read from the store, labelled on screen, never presented as analysis.                                                                                                                                                        |
| Declared simulation (محاكاة معلنة) | `SCAN_ENGINE=demo`, for development and smoke tests only: it calls no model, cites one stored verse as a general reminder and labels every insight; production refuses it (`config.py`).                                                                                                                               |
| Deferred (مؤجَّل)                  | The first production deploy and the Jenkins run (hosts pending), the developer panel, the download button on the share sheet, the profile skip path, camera discovery on real phones, the phase-1 coverage task, the deck and the video, and everything `docs/spec/master-prompt-v2.md` §28 lists after the challenge. |
