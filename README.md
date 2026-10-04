# TABSIRA — تَبْصِرَة

«انظر إلى العالم بعين الوحي». TABSIRA turns a photo into an insight (بصيرة) backed by one Quran verse and one hadith, in Arabic, as a phone-first web app that explains what it shows, where the text comes from and where its limits are.
Insights can be kept in a personal world, completed as a small step, shared as a card, published to a small social network («تبصرة تواصل») and placed on a real map («أطلس بصائر العالم») that a camera view discovers nearby.
Scripture is never written by a model: the model returns references only, the server reads the text from the store by id and shows it byte for byte with its stored hash.

Production: [tabsira.me](https://tabsira.me) (API at `api.tabsira.me`). Authors: Firas Ben Sassi and Ghazi Triki.

## Two ways to run it

| Where               | How                                                                                                                                                                                                                                                                 | Read                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| A laptop            | `make install`, `make migrate`, `make data` (once; it skips what is already imported), then `make dev` and open `http://tabsira.test` (plain HTTP on port 80, decision 49). Linux, macOS, or Linux in a virtual machine on Windows.                                 | [docs/SETUP.md](docs/SETUP.md)           |
| A production server | Directly on Ubuntu with systemd, gunicorn, pm2 and nginx, two hosts (application and data) joined by a VPN, deployed by `deploy/deploy.sh` with a pre-flight boot, rolling restarts and rollback. No Docker in production (decision 20); `make up` is not the path. | [docs/OPERATIONS.md](docs/OPERATIONS.md) |

The stack: `apps/web` (Next.js, React, TypeScript, Tailwind), `apps/api` (Python 3.12, FastAPI, SQLAlchemy, Alembic, managed with uv), `services/vision` (the object detector), PostgreSQL 18 with PostGIS, pgvector and TimescaleDB, Redis, and an S3-compatible bucket for consented photos.

## A reviewer's path

1. **The rain scene needs no account and no key.** The home page opens on the prepared rain scene, labelled «مثال موثّق مُعدّ»: its two insights, «الحياة في قطرة» and «الغرس الذي يتعدّاك», are read from the store by `GET /tutorial/rain` and never wait on a model. Open an insight, read its verse and the «لماذا ظهر هذا؟» sheet, keep it, complete its small step with «تمّ» and watch the world grow. A hadith appears only once an editor has recorded its dorar.net ruling; until then the insight says so and shows the verse alone (decisions 18 and 47).
2. **Without any AI key** a reviewer can also use the personal world «عالمي», the practice page «تمرينك», the public pages (`/terms`, `/privacy`, `/support`), sign-up by e-mail (nothing is sent while SMTP is not configured, and an unverified account can use everything private), and the admin area at `admin.tabsira.test` with an account made by `python -m src.cli.make_admin`. There is no demo account in the repository: a guest cookie is enough for everything the rain scene offers.
3. **A scan of your own photo** needs a provider key (`AI_OPENAI__API_KEY`, or `AI_PROVIDER=ovh` with the OVH keys). Without one, `SCAN_ENGINE=demo` runs a declared simulation that calls no model and labels every insight as a simulation; production refuses it, and nothing prepared, cached or simulated is ever presented as live analysis.
4. **`make smoke`** checks the pages, the API, the rain scene and, on a `.test` host, one trial scan; `make eval` runs the gold scenes and the chat cases and writes [docs/EVALUATION.md](docs/EVALUATION.md).

## Commands

```bash
make install     # all dependencies: web, api, vision, git hooks
make dev         # api + web (+ vision) with reload against tabsira.test
make migrate     # geodata chain, then app chain, then vectors chain
make data        # import corpora, ontology, learning path and vectors, once (DATA_FORCE=true to redo)
make test        # unit tests, web and api
make coverage    # tests with the 100 % threshold and HTML reports
make lint        # format check, lint, type check (web and api)
make format      # rewrite files the way the format check wants them
make eval        # gold scenes and the official contest cases
make smoke       # HTTP checks against a running app
make benchmark   # compare AI providers, detectors and rerankers on the same scenes
make up          # docker compose, which decision 20 ruled out: fails until a compose file exists
make stats       # a few lines about the code: size, tests, coverage, today
```

## Where things live

| What                                  | Where                                                                                                                                                         |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Decisions (they win over every spec)  | [docs/spec/DECISIONS.md](docs/spec/DECISIONS.md)                                                                                                              |
| Specifications                        | [docs/spec/master-prompt-v2.md](docs/spec/master-prompt-v2.md), the atlas and camera extension, «مسار» (learning path) and «تجربة» (UX rules) in `docs/spec/` |
| Plans, features and their tasks       | [docs/plans/README.md](docs/plans/README.md)                                                                                                                  |
| The day's log and the delivery table  | [docs/CHALLENGE-LOG.md](docs/CHALLENGE-LOG.md)                                                                                                                |
| Evaluation report                     | [docs/EVALUATION.md](docs/EVALUATION.md) (gold scenes, the twelve chat cases, cost and time per scan)                                                         |
| Benchmark of providers and retrieval  | [docs/BENCHMARK.md](docs/BENCHMARK.md)                                                                                                                        |
| Sources and licences of the scripture | [docs/SOURCES-AND-LICENSES.md](docs/SOURCES-AND-LICENSES.md)                                                                                                  |
| Privacy, admin, design, SEO           | [docs/PRIVACY.md](docs/PRIVACY.md), [docs/ADMIN.md](docs/ADMIN.md), [docs/DESIGN_DECISION.md](docs/DESIGN_DECISION.md), [docs/SEO.md](docs/SEO.md)            |
| Rules for people and coding agents    | [AGENTS.md](AGENTS.md)                                                                                                                                        |

## Licence

The object detector in `services/vision` depends on Ultralytics, which is AGPL-3.0, so the whole repository is AGPL-3.0 ([AGENTS.md](AGENTS.md); the licence text is in [services/vision/LICENSE](services/vision/LICENSE)). The scripture sources and their own terms are listed in [docs/SOURCES-AND-LICENSES.md](docs/SOURCES-AND-LICENSES.md). TABSIRA is free: no payment, plan or advertising anywhere (decision 43).
