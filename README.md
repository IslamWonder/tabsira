# 🌿 TABSIRA — تَبْصِرَة

> 📚 **Sources and licences first:** every Quran and hadith text, place name, map and model we use is listed with its licence in [docs/SOURCES-AND-LICENSES.md](docs/SOURCES-AND-LICENSES.md) and on the public page [tabsira.me/sources](https://tabsira.me/sources). The short list is [below](#-sources).

«انظر إلى العالم بعين الوحي». 📸 TABSIRA turns a photo into an insight (بصيرة) backed by one Quran verse and one hadith, in Arabic, as a phone-first web app that explains what it shows, where the text comes from and where its limits are.
🌍 Insights can be kept in a personal world, completed as a small step, shared as a card, published to a small social network («تبصرة تواصل») and placed on a real map («أطلس بصائر العالم») that a camera view discovers nearby.
🔒 Scripture is never written by a model: the model returns references only, the server reads the text from the store by id and shows it byte for byte with its stored hash.

🚀 Production: [tabsira.me](https://tabsira.me) (API at `api.tabsira.me`). 💻 Source: [github.com/IslamWonder/tabsira](https://github.com/IslamWonder/tabsira). ✍️ Authors: Firas Ben Sassi and Ghazi Triki.

## 📖 Sources

| Source                                                                                                                                                                                            | What we take from it                                                                                                                | Licence                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 🕋 [quranpedia.net](https://quranpedia.net), «مصحف حفص نسخة نصية» ([dumps](https://api.quranpedia.net/dumps))                                                                                     | The displayed Quran text (King Fahd Complex Uthmani, Hafs), corrected daily                                                         | [Quranpedia Data License](https://api.quranpedia.net/dumps/LICENSE.md)                                               |
| ✒️ [KFGQPC Uthmanic Script Hafs v22](https://fonts.qurancomplex.gov.sa)                                                                                                                           | The Quran font, served unchanged                                                                                                    | The King Fahd Complex's end-user licence, inside the font                                                            |
| 📜 [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api)                                                                                                                            | Seven hadith books and their graders' grades                                                                                        | [The Unlicense](https://unlicense.org)                                                                               |
| 📜 [mhashim6/Open-Hadith-Data](https://github.com/mhashim6/Open-Hadith-Data)                                                                                                                      | Musnad Ahmad and Sunan al-Darimi                                                                                                    | [ODbL 1.0](http://opendatacommons.org/licenses/odbl/1.0/), [DbCL 1.0](http://opendatacommons.org/licenses/dbcl/1.0/) |
| 🔎 [dorar.net](https://dorar.net) («الدرر السنية»)                                                                                                                                                | Rulings an editor may record by hand; its API is out of reach from a server, and the committee recommended other documented sources | dorar's terms (not reviewed)                                                                                         |
| 🗺️ [GeoNames](https://www.geonames.org) ([dump](https://download.geonames.org/export/dump/))                                                                                                      | Place names of the search and the atlas                                                                                             | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)                                                            |
| 🧭 [OpenStreetMap](https://www.openstreetmap.org/copyright) via [OpenFreeMap](https://openfreemap.org) and [OpenMapTiles](https://openmaptiles.org)                                               | The atlas map tiles                                                                                                                 | [ODbL 1.0](https://www.openstreetmap.org/copyright), with credit on the map                                          |
| 🌐 [MapLibre GL JS](https://maplibre.org)                                                                                                                                                         | Map rendering                                                                                                                       | BSD-3-Clause                                                                                                         |
| 👁️ [Ultralytics YOLOE](https://github.com/ultralytics/ultralytics)                                                                                                                                | Object detection in `services/vision`                                                                                               | [GNU AGPL 3.0](https://www.gnu.org/licenses/agpl-3.0.html), hence the whole repository                               |
| 🔤 [Readex Pro](https://fonts.google.com/specimen/Readex+Pro), [Reem Kufi](https://fonts.google.com/specimen/Reem+Kufi), [Noto Naskh Arabic](https://fonts.google.com/specimen/Noto+Naskh+Arabic) | Interface fonts, self-hosted                                                                                                        | [SIL OFL 1.1](https://openfontlicense.org)                                                                           |
| 🧩 The project's own data                                                                                                                                                                         | The annotated Quran corpus, the enriched Sunnah file, the world ontology, «مسار»: retrieval aids only, never shown as scripture     | The project's own                                                                                                    |

🤖 The models the running app calls (scene analysis, search vectors, verification, the explanation, the chat) come from [OpenAI](https://openai.com/policies/terms-of-use) and [OVHcloud AI Endpoints](https://endpoints.ai.cloud.ovh.net), under each provider's terms. The tools used to build TABSIRA, and what each did, are in [docs/SOURCES-AND-LICENSES.md](docs/SOURCES-AND-LICENSES.md#tools-used-to-build-tabsira). The contest's own references: the [participant's guide](https://islamicaich.org/files/HackathonFile/da2OrbRMEsNrIQaoq8z6jEv26opKXdQmq1i0XfXo.pdf) and the [reference pack](https://islamicaich.org/files/HackathonFile/ZA1IoQnh5S1tuLFiBghyT7U2HYN6IpzNDg9vamHW.pdf), summarised in [docs/spec/contest-guide.md](docs/spec/contest-guide.md) and [docs/spec/contest-reference.md](docs/spec/contest-reference.md).

## 🛠️ Two ways to run it

| Where                  | How                                                                                                                                                                                                                                                                 | Read                                     |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| 💻 A laptop            | `make install`, `make migrate`, `make data` (once; it skips what is already imported), then `make dev` and open `http://tabsira.test` (plain HTTP on port 80, decision 49). Linux, macOS, or Linux in a virtual machine on Windows.                                 | [docs/SETUP.md](docs/SETUP.md)           |
| 🖥️ A production server | Directly on Ubuntu with systemd, gunicorn, pm2 and nginx, two hosts (application and data) joined by a VPN, deployed by `deploy/deploy.sh` with a pre-flight boot, rolling restarts and rollback. No Docker in production (decision 20); `make up` is not the path. | [docs/OPERATIONS.md](docs/OPERATIONS.md) |

🧱 The stack: `apps/web` (Next.js, React, TypeScript, Tailwind), `apps/api` (Python 3.12, FastAPI, SQLAlchemy, Alembic, managed with uv), `services/vision` (the object detector), PostgreSQL 18 with PostGIS, pgvector and TimescaleDB, Redis, and an S3-compatible bucket for consented photos.

## 🧑‍⚖️ A reviewer's path

1. 🌧️ **The rain scene needs no account and no key.** The home page opens on the prepared rain scene, labelled «مثال موثّق مُعدّ»: its two insights, «الحياة في قطرة» and «الغرس الذي يتعدّاك», are read from the store by `GET /tutorial/rain` and never wait on a model. Open an insight, read its verse and the «لماذا ظهر هذا؟» sheet, keep it, complete its small step with «تمّ» and watch the world grow. The hadith is shown from its book with its reference and, where its dataset grades it, the first grader's ruling («حكم الألباني: صحيح», decision 69, switch `hadith_ruling`); only a hadith an editor ruled out is left out, and the insight then shows the verse alone.
2. 🔑 **Without any AI key** a reviewer can also use the personal world «عالمي», the practice page «تمرينك», the public pages (`/terms`, `/privacy`, `/support`, `/sources`), sign-up by e-mail (nothing is sent while SMTP is not configured, and an unverified account can use everything private), and the admin area at `admin.tabsira.test` with an account made by `python -m src.cli.make_admin`. There is no demo account in the repository: a guest cookie is enough for everything the rain scene offers.
3. 📷 **A scan of your own photo** needs a provider key (`AI_OPENAI__API_KEY`, or `AI_PROVIDER=ovh` with the OVH keys). Without one, `SCAN_ENGINE=demo` runs a declared simulation that calls no model and labels every insight as a simulation; production refuses it, and nothing prepared, cached or simulated is ever presented as live analysis.
4. ✅ **`make smoke`** checks the pages, the API, the rain scene and, on a `.test` host, one trial scan; `make eval` runs the gold scenes and the chat cases and writes [docs/EVALUATION.md](docs/EVALUATION.md).

## ⌨️ Commands

```bash
make install     # all dependencies: web, api, vision, git hooks
make dev         # api + web (+ vision) with reload against tabsira.test
make migrate     # geodata chain, then app chain, then vectors chain
make data        # install GeoNames (when configured), the corpus and the vectors, once (DATA_FORCE=true to redo)
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

## 🗂️ Where things live

| What                                    | Where                                                                                                                                                         |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 📚 Sources and licences                 | [docs/SOURCES-AND-LICENSES.md](docs/SOURCES-AND-LICENSES.md), versions and hashes in [docs/ASSET_MANIFEST.md](docs/ASSET_MANIFEST.md)                         |
| ⚖️ Decisions (they win over every spec) | [docs/spec/DECISIONS.md](docs/spec/DECISIONS.md)                                                                                                              |
| 📐 Specifications                       | [docs/spec/master-prompt-v2.md](docs/spec/master-prompt-v2.md), the atlas and camera extension, «مسار» (learning path) and «تجربة» (UX rules) in `docs/spec/` |
| 🏆 The contest's rules                  | [docs/spec/contest-guide.md](docs/spec/contest-guide.md), [docs/spec/contest-reference.md](docs/spec/contest-reference.md)                                    |
| 🗺️ Plans, features and their tasks      | [docs/plans/README.md](docs/plans/README.md)                                                                                                                  |
| 📅 The day's log and the delivery table | [docs/CHALLENGE-LOG.md](docs/CHALLENGE-LOG.md)                                                                                                                |
| 📊 Evaluation report                    | [docs/EVALUATION.md](docs/EVALUATION.md) (gold scenes, the twelve chat cases, cost and time per scan)                                                         |
| 🏁 Benchmark of providers and retrieval | [docs/BENCHMARK.md](docs/BENCHMARK.md)                                                                                                                        |
| 🔐 Privacy, admin, design, SEO          | [docs/PRIVACY.md](docs/PRIVACY.md), [docs/ADMIN.md](docs/ADMIN.md), [docs/DESIGN_DECISION.md](docs/DESIGN_DECISION.md), [docs/SEO.md](docs/SEO.md)            |
| 🤝 Rules for people and coding agents   | [AGENTS.md](AGENTS.md)                                                                                                                                        |

## 📘 Glossary

| Term                               | Meaning                                                                                                                                  |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 💡 بصيرة (basira), insight         | What a scan produces: a reading of the scene backed by one verse and one hadith, with an explanation labelled as AI-assisted reflection  |
| 🌿 تبصرة (tabsira)                 | The app's name: "giving insight"; written without an "h"                                                                                 |
| 🌍 عالمي, the personal world       | Where a member keeps their insights and watches them grow as they complete small steps                                                   |
| 🎯 تمرينك, practice                | The page of small steps to live an insight                                                                                               |
| 🧭 مسار (masar), learning path     | The order in which concepts are met, from the root to the branch                                                                         |
| 🎨 تجربة (tajriba)                 | The UX rules of the app, built on the Laws of UX                                                                                         |
| 💬 تبصرة تواصل                     | The small social network: posts, follows, reactions                                                                                      |
| 🗺️ أطلس بصائر العالم               | The world atlas: insights placed on a real map at an approximate location the owner chose                                                |
| 📷 Camera discovery                | A camera view that finds atlas entries nearby                                                                                            |
| 🤲 كفالة بصيرة, sponsoring         | Taking care of an atlas entry whose owner left                                                                                           |
| ❓ «لماذا ظهر هذا؟»                | The sheet that explains why these texts were chosen: what the scene showed, the concept, the sources                                     |
| 🔗 وجه الصلة                       | The line saying how a text meets the scene; part of the generated explanation, never scripture                                           |
| 🕋 Verse (آية) and its reference   | A Quran verse shown with its surah and number, from quranpedia's text                                                                    |
| 📜 Hadith (حديث)                   | A report of what the Prophet ﷺ said, did or approved, shown from its book with its number                                                |
| 📚 الكتب التسعة, the nine books    | Bukhari, Muslim, Abu Dawud, al-Tirmidhi, al-Nasa'i, Ibn Majah, Malik's Muwatta, Musnad Ahmad, Sunan al-Darimi                            |
| 🤝 الصحيحان, the two Sahihs        | Bukhari and Muslim, whose sahih hadiths the contest accepts without a further ruling                                                     |
| ⚖️ حكم, ruling (grade)             | A scholar's judgement on a hadith's soundness; TABSIRA shows the first grader's ruling of the dataset and never lets a model state one   |
| ✅ صحيح, sound                     | A hadith whose chain is connected by trustworthy, precise narrators, with no hidden defect                                               |
| 🟢 حسن, good                       | Close to sahih, with a narrator of slightly lesser precision                                                                             |
| 🟠 ضعيف, weak                      | Missing a condition of the sahih or the hasan                                                                                            |
| ⛔ موضوع, fabricated               | Falsely attributed to the Prophet ﷺ                                                                                                      |
| 🔗 إسناد, chain, and متن, text     | The chain of narrators, and the words they transmit                                                                                      |
| 🧾 موقوف, مقطوع, مرسل              | Reports that stop at a Companion, at a Successor, or that skip the Companion                                                             |
| 🔒 Byte for byte, stored hash      | Scripture is displayed exactly as stored, and its SHA-256 is checked against the one recorded at import                                  |
| 🚦 Evidence gate                   | The server step that accepts or refuses a verse and a hadith for an insight; the model proposes ids, the gate decides                    |
| 🔎 Hybrid retrieval, reranking     | Finding candidate texts by words, concepts and vectors together, then ordering the best few with a small model that answers numbers only |
| 🧠 pgvector, PostGIS               | PostgreSQL extensions for vector search and for geography                                                                                |
| 🎛️ Feature switches                | `DISABLED_FEATURES` and `ENABLED_FEATURES` in `.env` (decision 63), e.g. `hadith_ruling` on by default, `quran_source_link` off          |
| 🧪 Simulation (`SCAN_ENGINE=demo`) | A declared run that calls no model, labelled as a simulation, refused in production                                                      |

## 📄 Licence

🛡️ The object detector in `services/vision` depends on Ultralytics, which is AGPL-3.0, so the whole repository is AGPL-3.0 ([LICENSE](LICENSE), [AGENTS.md](AGENTS.md)). The scripture sources and their own terms are listed in [docs/SOURCES-AND-LICENSES.md](docs/SOURCES-AND-LICENSES.md). 💚 TABSIRA is free: no payment, plan or advertising anywhere (decision 43).
