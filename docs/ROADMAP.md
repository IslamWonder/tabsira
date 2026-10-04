# Roadmap

The order in which TABSIRA is built. Each line becomes one or more atomic commits. Scope comes from `docs/spec/DECISIONS.md`; nothing here adds scope.

## Wave 1 — foundations

- [x] Repository tooling: pnpm workspace, Biome, prettier, markdownlint, typos, jscpd, check-only pre-commit hook, security and audit scripts, Makefile.
- [x] Local `tabsira.test`: PostgreSQL extensions (PostGIS, pgvector, TimescaleDB and the rest), databases `tabsira` and `tabsira_test`, nginx with mkcert.
- [x] API skeleton: settings, database, `app` and `geodata` Alembic chains, health, error handling, 100 % coverage.
- [x] Provider research (OVH, OpenAI) and the corpus audit: `docs/research/ai-providers.md`, `docs/ASSET_MANIFEST.md`.
- [x] Design gate: direction C with a light theme in A's colours (`docs/DESIGN_DECISION.md`).

## Wave 2 — data, accounts, shell

- [ ] Scripture store: Quran and nine-books hadith tables with stored hashes, read-only; importers; Sunnah signals after the cp720 repair; search copy normalised separately.
- [ ] World ontology and learning-path importers (`masar.md` as versioned data), `OntologyCandidate`.
- [x] Accounts: email and password, Google (OIDC with PKCE), sessions, guest merge, profile with the three optional questions, consent records, deletion and export.
- [ ] Web shell: Next.js app, design tokens for both themes, self-hosted fonts, PWA, navigation, messages module, generated API client, 100 % coverage.
- [x] Vision service: YOLOE / YOLO-World over HTTP, AGPL-3.0.
- [x] Jenkinsfile with SonarQube and the quality gate.
- [ ] Zero-downtime deploy scripts for pm2 and gunicorn, production provisioning for `tabsira.me` and the VPN data host — after the features (decision 20).

## Wave 3 — the insight

- [ ] Provider adapters (OVH, OpenAI) and `make benchmark`; defaults per stage set from measurements.
- [ ] Pipeline: image validation, moderation, detector, scene analysis, ontology resolver, insight planner, learning planner, hybrid retrieval (full-text plus pgvector, RRF), cross-encoder rerank, evidence gate with leak guard, composer.
- [ ] Scans API with honest progress over SSE; focus and clarification; the rain tutorial scene as prepared data.
- [ ] Insight screen, «لماذا ظهر هذا؟», the small step, chat limited to three messages, «تمّ» with idempotent save.
- [ ] Exposure log and diversity of equal-weight texts; hidden treasure.
- [ ] Personal world: fog map with places per learning-path domain.
- [ ] Gamification (decision 27): practice ranks, streak, daily quest, sky of meanings, badges, victory banner, world growth.

## Wave 4 — sharing, social, atlas

- [ ] Share card rendered with real fonts; public insight page.
- [ ] «تبصرة تواصل»: posts from verified insights, feeds «لك» and «أتابع» with cursors, follow, like, comments, bookmarks, reports, blocks, moderation states.
- [ ] Photo storage with consent (S3 in production, disk locally), EXIF read then stripped.
- [x] GeoNames import into `geodata`, place search, reverse lookup and the deterministic approximation grid.
- [ ] Private capture location and public map entry; publish and withdraw.
- [ ] «أطلس بصائر العالم»: MapLibre map with clusters, filters, place pages.
- [ ] «اكتشف البصائر حولك»: camera discovery level A, level B with orientation, level C behind a flag.

## Wave 5 — operations and proof

- [ ] Admin area (sqladmin) with two-factor sign-in, audit log, moderation queue; scripture read-only.
- [ ] TimescaleDB hypertables for scan events, AI calls, exposures, impressions, moderation and audit.
- [ ] Gold scenes and the twelve official cases (`make eval`), smoke tests, developer inspector.
- [ ] Terms and privacy page matching every data flow; robots, sitemap, metadata, icons.
- [ ] Reviews: scripture integrity, privacy and security.
- [ ] Delivery documents: sources and licences, benchmark, evaluation report, operations.
