# AGENTS.md — rules for AI coding agents working on TABSIRA

For Claude Code, Copilot, Cursor, Codex and any other agent. Claude Code reads `CLAUDE.md`, which holds the single line `@AGENTS.md`.

Read first, in this order:

1. `docs/spec/DECISIONS.md` — what the owners decided when specs disagree. It wins over every other document.
2. `docs/spec/master-prompt-v2.md` — what to build.
3. `docs/spec/extension-atlas-camera.md` — the world atlas and the camera discovery.
4. `docs/spec/masar.md` (learning path) and `docs/spec/tajriba.md` (UX rules, Laws of UX) inside their own scope.
5. `docs/plans/README.md` — the features and their tasks; take a task the way it says.

## Project

TABSIRA (تَبْصِرَة, no "h") turns a photo into an insight (بصيرة) backed by one Quran verse and one hadith, in Arabic, as a phone-first PWA. Insights can be saved in a personal world, shared, published to a small social network («تبصرة تواصل») and placed on a real map («أطلس بصائر العالم») that a camera view can discover nearby. Authors: Firas Ben Sassi and Ghazi Triki.

- Production: `https://tabsira.me` (`api.tabsira.me` for the API).
- Local development: `https://tabsira.test` (`api.tabsira.test`), TLS by mkcert. Production files never contain `.test`; `.test` defaults in code are development-only.

## Stack

- `apps/web` — Next.js (App Router), React, TypeScript, Tailwind. Presentation, public pages, share cards, map and camera views. Runs under pm2 in cluster mode.
- `apps/api` — Python 3.12, FastAPI, Pydantic, SQLAlchemy (async) and Alembic, managed with uv. All AI, data, account, social and geo logic. Runs under gunicorn with uvicorn workers.
- `services/vision` — the object detector (Ultralytics YOLOE / YOLO-World) behind a small HTTP service. Ultralytics is AGPL-3.0, so the whole repository is AGPL-3.0.
- PostgreSQL 18 with PostGIS and pgvector. One database, two schemas, two Alembic chains: `geodata` (GeoNames, migrated first) and `app` (everything else). Tests use a separate `tabsira_test` database.
- S3-compatible storage for consented photos; local disk on `tabsira.test`.
- The API publishes OpenAPI; the web client types are generated from it. Never hand-write a type twice.

## Commands

Keep every one working; never rename them.

```bash
make install     # all dependencies: web, api, vision, git hooks
make dev         # api + web (+ vision) with reload against tabsira.test
make migrate     # geodata chain, then app chain
make data        # import corpora, ontology and learning path; build indexes
make test        # unit tests, web and api
make coverage    # tests with the 100 % threshold and HTML reports
make lint        # format check, lint, type check (web and api)
make format      # rewrite files the way the format check wants them
make eval        # gold scenes and the official contest cases
make smoke       # HTTP checks against a running app
make benchmark   # compare AI providers, detectors and rerankers on the same scenes
make up          # docker compose up, whole stack
make stats       # a few lines about the code: size, tests, coverage, today
```

Before you say a task is done: `make lint && make coverage` pass, and `make smoke` passes if you touched a route.

## Git workflow

- **One commit = one logical change.** A refactor, a feature and a formatting pass are three commits. Tests go in the same commit as the code they test.
- **Commit message: a single line**, imperative, at most 72 characters, prefixed by its area. No body.
  `api: reject scripture text found in model output`
- **No co-author, ever.** No `Co-Authored-By`, no "Generated with", no tool or model name in commits, code, comments or docs. The author is the human who runs you.
- Work on `main`. Commit locally; **never push** — the owners push. Never force, never rewrite history, never skip hooks (`--no-verify` is forbidden).
- Run `make format` before committing; the pre-commit hook refuses unformatted staged files.
- Never commit secrets, `.env` files, user photos, corpora larger than 5 MB, or generated reports.

## Boundaries

**Always**

- Read the existing code before adding code, and follow its naming and structure.
- Check the latest version of a dependency in its registry (npm, PyPI) when you add it. Never guess a version.
- Add every new configuration key to the typed settings and to `.env.example` in the same commit.
- Update the terms and privacy text in the same commit as any new data flow.
- Update the step's status in `docs/plans/` in the same commit as the change.
- Say plainly what you did not do, what failed, and what you could not verify.

**Ask first**

- Adding a service, a new top-level folder, or a third-party network call.
- Changing an API contract, a migration already committed, or a public URL.
- Anything touching authentication, photo storage, location privacy, or what is shown as Quran or hadith.
- Any user-interface work before a design direction is recorded in `docs/DESIGN_DECISION.md`. Propose three directions, then **stop** until the owners choose.

**Never**

- Write, complete, shorten, normalise or "fix" Quran or hadith text. It is loaded from the database by id and displayed byte for byte, with its stored hash.
- Let a model produce scripture. Model output carries evidence ids only; scripture found in it is rejected.
- Infer religion, age, gender, health, identity or intent from a photo, a name, a place or behaviour.
- Publish a precise location the owner did not choose, or derive one from a model's answer. Approximate locations are computed on the server; the exact point never reaches a public API.
- Lower a coverage threshold, delete a failing test, or mark a test skipped to get green.
- Add analytics, trackers, CDN assets or any third-party request from the visitor's browser. The documented exceptions: map tiles (decision 9) and Google Analytics only when `GA_MEASUREMENT_ID` is set and only after consent (decision 28).
- Use gpt-oss models.
- Add any payment, paid plan, subscription, premium feature or advertising. TABSIRA is free (decision 43).
- Name any other project of the owners in code, comments, docs, data or commit messages. Say "the earlier prototype" for the earlier version of this product; describe anything else by what it does. On the main machine a commit hook refuses such names.
- Present a prepared example, a cached result or demo data as live analysis.

## Code style

- TypeScript strict, no `any`. Python fully typed and checked; ruff with the rules in `apps/api/pyproject.toml`.
- Biome formats and lints TypeScript, JavaScript and JSON; prettier formats Markdown; shfmt formats shell.
- Small functions with one job. Each pipeline stage takes a schema and returns a schema.
- Comments explain why, not what. No commented-out code.
- User-visible text is Arabic, right-to-left, and lives in one messages module per app, not inline.
- File and folder names are ASCII, lower-case, no spaces. Source files use LF line endings.
- Hover must not move anything. Motion happens on display and on events only, and respects reduced motion.

## Testing

**Fast loop, one gate.** While you work, run only the tests of what you touch (`uv run pytest -n 1 tests/<area>`, `pnpm --filter @tabsira/web exec vitest related --maxWorkers=1 <files>`); several agents share one machine, so never `-n auto` or an uncapped vitest; run the full suite with coverage once, at the end, before you hand over, under the shared lock so two gates never overlap (`flock /tmp/tabsira-gate.lock env PYTEST_WORKERS=2 make coverage` on Linux; inside the lock the gate may use two workers). No repeated full runs, no live demos unless the task asks for one, and no screenshots unless the owners ask for them: they cost time and prove little that the tests and the accessibility check do not. Before reporting, rebase your branch onto the latest `main` yourself, resolve the conflicts, re-chain your migration onto the current head, and run the gate once on the rebased branch.

- **Phase mode (owners' decision 42).** During a build phase a branch merges when `make lint` passes and the existing tests of the areas it touches pass (`uv run pytest -n 2 tests/<area>`, `vitest related`); new code may land without its tests and the full coverage gate is not run per merge. Each phase ends with a test task that writes the missing tests and brings `make coverage` back to 100 % before release. Exception: code that decides or displays Quran or hadith text, the scripture guards, authentication, sessions, privacy and photo or location handling keep their tests in the same commit and their review before merge.
- 100 % line, branch and function coverage in `apps/web`, `apps/api` and `services/vision` at the end of every phase. An exclusion needs a written reason in the coverage config.
- Unit tests never touch the network, a model or a real external service. Mock at the provider boundary. Database tests use a test database only: `tabsira_test` when one agent works on the machine; when several do, each worktree points `TEST_DATABASE_URL` at its own copy of `tabsira_template` (for example `tabsira_<task>_test`), since parallel runs on the same names break each other.
- A bug fix starts with a test that fails.
- Compare displayed scripture with its stored hash in tests.

## Subagents

Project subagents live in `.claude/agents/`. Each one sets its model and reasoning effort for its job: fast and light for searching, stronger for implementation, strongest with high effort for scripture integrity, privacy and security review. Use the matching agent instead of a general one.

## Working across our machines

One Mac, two Windows laptops that develop inside Linux virtual machines, one Windows laptop for testing.

- Every command must behave the same on Linux, macOS and inside Docker. No PowerShell-only or macOS-only steps.
- Never rely on case-insensitive paths.
- Bind servers to `127.0.0.1`; connect to the database on `127.0.0.1`, not `localhost`.
- Scheduled work runs in exactly one process, never once per worker.

## Lessons already paid for

- Vision models return boxes in their own coordinate system: GPT in pixels of the image it received, Qwen 3.x on a 0–1000 grid even when asked for pixels. The provider setting `BOX_COORDINATES` says which; convert to 0–1 ratios on the server and drop boxes outside the image.
- Reranking with a large language model was the slowest stage (about 20 s of a 30–45 s scan). Measure a cross-encoder before choosing.
- When the database is down the first page must still load: short connect timeout, an error handler, no unhandled rejection.
- A page-level CSS transform breaks `position: fixed` children. Animate opacity on wrappers.
- In nginx, a location that sets a header drops the headers inherited from the server block.
- `NEXT_PUBLIC_*` values are baked at build time. A build made with a local URL carries it in every canonical and share tag.
- Sensitive scenes: never show the image back, never store it.
- Promises in legal text are code: change the terms and the behaviour together.
- `processed_sunnah_data.json` is UTF-8 that was decoded as cp720 and saved again. Repair it losslessly (`s.encode("cp720").decode("utf-8")`) and verify; it is a ranking signal, never displayed text.
- A regular expression inside a template literal loses its backslashes; a `*/` inside a block comment ends it.
- GeoJSON order is `[longitude, latitude]`. A coordinate of zero is a value, not a missing one.

## When you are unsure

Stop and ask one precise question. A wrong guess costs more than a question.
