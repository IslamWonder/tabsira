# Owner decisions

These decisions resolve the conflicts between the specification documents. This file wins over every other document in `docs/spec/`. A later decision is added at the end with its date; an earlier one is never edited silently.

## Documents and their standing

| Document | Standing |
| --- | --- |
| `master-prompt-v2.md` | **Governs** what to build, except where this file says otherwise |
| `extension-atlas-camera.md` | **In scope**: world atlas and camera discovery, adapted below |
| `masar.md` | Learning path, binding inside its scope, with the changes of v2 §29 |
| `tajriba.md` | UX rules mapped to the Laws of UX, binding inside its scope, with the changes of v2 §29 |
| `master-prompt-v1.md` | Superseded by v2; kept for reference only |
| `differences-v1-v2.md`, `owner-comments.md` | Record of why v2 differs from v1 |

## 4 October 2026 — start of the rewrite

1. **Scope.** v2, plus the atlas and camera extension, plus a core social network. There are no day-by-day cuts: everything is built; unfinished features stay behind their feature flag and never break the core journey.
2. **Social network («تبصرة تواصل»)** is ported from the reference project and replaces v2 §18's "public page only": posts made from verified Basiras, a feed with «لك» and «أتابع» tabs and cursor pagination, follow, like, comments, bookmark, report, block, and moderation states (`draft`, `pending_review`, `published`, `rejected`, `removed`) with an AI guard. Out of scope: reposts, polls, mentions, push notifications, direct messages.
3. **Lens is dropped**, including the extension's «انظر بعين هذه البصيرة». The hidden treasure (v2 §17) is the only "return" mechanic.
4. **AI providers.** OVH (Qwen) and OpenAI are both wired behind one adapter, one settings block per provider. The benchmark runs first; its measured result sets the default model of each stage.
5. **Detector.** Ultralytics YOLOE / YOLO-World in `services/vision`, reached only over HTTP and behind the `DETECTOR` interface so it can be swapped. Ultralytics is AGPL-3.0, so `services/vision` is AGPL-3.0. The licence of the rest of the repository is **pending the owners' choice**; no `LICENSE` file is added until then.
6. **Corpora.**
   - Quran: `final_complete_verses_20251202_194512.json` (Firas's annotated corpus). Its text is checked at import against the Tanzil Uthmani (Hafs) edition and the result is recorded in `docs/ASSET_MANIFEST.md`.
   - Hadith displayed text: the nine books from the fawazahmed0 `hadith-api` Arabic editions, with grades exactly as given.
   - `processed_sunnah_data.json`: ranking signals only, after a lossless cp720 repair. Never displayed.
7. **Design gate.** Three directions are published for the owners. No interface work starts before `docs/DESIGN_DECISION.md` records a choice; API, data, CI and deployment proceed meanwhile.
8. **Photos.** Stored with the account owner's consent in S3-compatible storage in production and on local disk on `tabsira.test`, under v2 §19's rules. A photo is copied to a public location only when its owner publishes.
9. **Atlas and camera, adapted to the reference project.**
   - Place search and reverse lookup use GeoNames imported into the `geodata` schema, so no geocoding request leaves our servers.
   - The map uses MapLibre with OpenFreeMap tiles. These tiles are the one documented exception to "no third-party request from the visitor's browser", named in the terms page.
   - The camera discovery ships levels A (places) and B (direction); level C (anchoring) stays behind a flag and is not announced until it is proven on devices.
10. **Domains.** Production `tabsira.me`; local development `tabsira.test` with mkcert certificates.
11. **Delivery tooling** is ported from the reference project: Jenkinsfile with a SonarQube scan and quality gate, ruff for Python, Biome for TypeScript and JSON, prettier for Markdown, a check-only pre-commit hook, the `app` and `geodata` schemas with two Alembic chains, and zero-downtime deploys (pm2 reload one instance at a time; gunicorn workers replaced one at a time). Jenkins and SonarQube addresses are configuration, never hard-coded.
12. **Git.** One logical change per commit, a one-line message, no co-author or tool attribution. Agents commit locally; the owners push.
13. **TimescaleDB** for append-only time series, as hypertables partitioned on their time column: scan stage events and timings, AI calls (provider, model, tokens, cost, latency), evidence and insight exposures, feed and map impressions, moderation actions and the admin audit log. Ordinary tables keep ordinary timestamps; retention and compression policies are set per hypertable.
14. **Admin area** ported from the reference project: sqladmin at `/admin` on the API, sign-in with a real account that has `is_admin`, two-factor code when enrolled, twelve-hour session, CSRF, rate limit and an audit log. Views: users, profiles, insights, posts, comments, reports, blocks, moderation queue, map entries and location reports, ontology candidates, learning-path versions, AI cost and latency, GeoNames. **Quran and hadith records are read-only in the admin**: no edit, create or delete form exists for them.
