# Sources and licences

What TABSIRA is built from, under which terms, what each licence asks of us, and where we do it. Versions, file hashes and counts are in `docs/ASSET_MANIFEST.md`; the owners' choices are decisions 16 to 19 in `docs/spec/DECISIONS.md`. The page `/sources` («المصادر والتراخيص», `apps/web/src/messages/legal.ts`) is the public side of this file: change both together.

Two different uses carry different duties:

- **Inside the app** (what a visitor sees on tabsira.me).
- **The archives in the owners' public bucket** (`corpus/`, `geodata/`, `vectors/` on `s3-v2.riastorage.com/tabsira`): anyone can download them, so they are a republication of the data as a dataset.

| Source                                                                      | Used for                                                | Licence                                                          | Inside the app                                                                                                                             | In the public archives                                                             |
| --------------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| quranpedia.net, «مصحف حفص نسخة نصية»                                        | Displayed Quran text, daily corrections                 | Quranpedia.net Data License 2026-10-01                           | No credit required; a link is appreciated. Credited with a link on `/sources`                                                              | **Required:** credit, link and dump version. In `NOTICE.txt` of the corpus archive |
| fawazahmed0 `hadith-api`                                                    | Seven hadith books                                      | The Unlicense                                                    | Nothing required; named on `/sources`                                                                                                      | Nothing required; named in `NOTICE.txt`                                            |
| mhashim6 `Open-Hadith-Data`                                                 | Musnad Ahmad, Sunan al-Darimi                           | ODbL 1.0 (database), DbCL 1.0 (contents)                         | **Required:** the project's notice on a public use. On `/sources`, verbatim                                                                | **Required:** the derived rows shared under ODbL with the notice. In `NOTICE.txt`  |
| dorar.net                                                                   | Hadith rulings recorded by editors, verification links  | dorar's terms (not reviewed)                                     | The dorar page of each ruling; named on `/sources`                                                                                         | Rulings are not in the archives                                                    |
| GeoNames                                                                    | Place names of the search and the atlas                 | CC BY 4.0                                                        | **Required:** attribution and the licence link. On `/sources` and in the map's credit line                                                 | **Required:** attribution, licence link, changes made. In `geodata/NOTICE.txt`     |
| OpenStreetMap, via OpenFreeMap and OpenMapTiles                             | Map tiles of the atlas (decision 9)                     | ODbL 1.0 (OSM data); OpenFreeMap and OpenMapTiles ask for credit | **Required:** «© OpenStreetMap» linked to its copyright page, on the map. Done in the map's credit line, with OpenFreeMap and OpenMapTiles | Not in the archives                                                                |
| Ultralytics YOLOE                                                           | Object detection (`services/vision`)                    | GNU AGPL 3.0                                                     | **Required:** the whole program under AGPL, and its source offered to users over the network. Root `LICENSE`, source link on `/sources`    | Not in the archives                                                                |
| Readex Pro, Reem Kufi, Noto Naskh Arabic                                    | Interface fonts, self-hosted                            | SIL OFL 1.1                                                      | Nothing required when embedded; named on `/sources`                                                                                        | —                                                                                  |
| MapLibre GL JS                                                              | Map rendering                                           | BSD-3-Clause                                                     | Licence kept in the bundled package; named on `/sources`                                                                                   | —                                                                                  |
| KFGQPC Uthmanic Script Hafs v22                                             | Quran font of the pages and the share card, self-hosted | KFGQPC end-user licence (in the font file)                       | Use, copy and distribute free of cost; never sold or modified. Served byte for byte with its licence inside; named on `/sources`           | Not in the archives                                                                |
| Annotated Quran corpus, enriched Sunnah file, world ontology, learning path | Retrieval aids, ontology, «مسار»                        | The project's own                                                | Never shown as scripture                                                                                                                   | Named in `NOTICE.txt`                                                              |

## Quran text: quranpedia.net

- **What.** Mushaf 2, «مصحف حفص نسخة نصية»: the King Fahd Complex Uthmani text of Hafs as quranpedia publishes it, from its official versioned dumps (`https://api.quranpedia.net/dumps`), each file checked against the SHA-256 of the dump manifest. The store holds dump `2026-10-03`. Corrections come from its changes feed (`/v1/changes`), applied daily by `src.cli.sync_quran`.
- **Licence** (`https://api.quranpedia.net/dumps/LICENSE.md`, version 2026-10-01, read again on 5 October 2026). The Quran text is the shared heritage of the ummah; the digitisation, structuring, verification, diacritical correction and metadata are the work of the quranpedia team. Use inside apps and websites is free and needs **no attribution**; a visible link to `https://quranpedia.net` is appreciated. Republishing the data, whole or in part, **as a downloadable database or dataset** requires (1) crediting Quranpedia.net with a link and (2) stating the dump version. A published copy must be kept current through the changes feed; the data comes without warranty.
- **Inside the app.** No link is required, so the verse card carries none by default (commit `ce5290a`); the `quran_source_link` switch brings it back. The appreciated link is on `/sources`, with the dump version. The API still returns each verse's quranpedia page (`source_url`) for anyone who wants it.
- **In the corpus archive.** It is a downloadable dataset, so `NOTICE.txt` names Quranpedia.net, links to it, states the dump version (filled in by `scripts/corpus/export.sh` from the store) and repeats the duty to keep copies current. The archive exported on 2026-10-04 predates the file: its `NOTICE.txt` sits beside it in the bucket (`corpus/NOTICE.txt`) until the next export embeds it. A copy installed by TABSIRA stays current through the daily sync.
- **Usage policy** (`https://quranpedia.net/api-docs#usage-policy`). Dumps rather than crawling the API, the changes feed to stay current, at most 120 requests a minute. The importer makes three requests per run, the sync one plus one per corrected verse, spaced 0.6 s apart, with `User-Agent: tabsira/0.1 (+https://tabsira.me)`.
- **Not used.** The dumps also carry word morphology (Quranic Arabic Corpus, GNU GPL, whose use requires naming it with a link) and i'rab syntax (The Quranic Treebank, MIT). Neither is downloaded; if one ever is, its own terms apply.

## Quran font: KFGQPC Uthmanic Script Hafs v22

`apps/web/src/fonts/UthmanicHafs_V22.ttf`, made by the King Fahd Glorious Quran Printing Complex, downloaded from quranpedia.net, which renders mushaf 2 with it (decision 16; source and date in `apps/web/src/fonts/README.md`). It is self-hosted since commit `bae5fa62`: the pages load it through `next/font/local` and the share card reads it from disk.

- **Licence.** The end-user licence agreement inside the font file (its `name` table, read on 5 October 2026): free of cost, the rights to use, copy and distribute it; it may not be sold, modified, altered, translated, reverse engineered, decompiled or reproduced; it comes as is. The Complex keeps the copyright.
- **Our use.** The file is served and read unchanged, with the licence inside it: no subsetting, no conversion, no renamed font. `next/font/local` only copies it under a hashed name. Nothing is sold (decision 43). It is named on `/sources`. A future change that subsets, converts or edits it is not allowed by these terms.

## Hadith: fawazahmed0 `hadith-api`

- **What.** The Arabic editions of al-Bukhari, Muslim, Abu Dawud, al-Tirmidhi, al-Nasa'i, Ibn Majah and Malik, pinned to commit `df57907be35291c91ad6a6691180e22ca9920784` and checked by SHA-256.
- **Licence.** The Unlicense (`data/cache/hadith/LICENSE.txt`): a dedication to the public domain; no condition. The editions name no source and give "Unknown" as the author of the Arabic text, so its provenance is not documented. We name the project anyway, on `/sources` and in `NOTICE.txt`.
- **Grades.** Where the dataset has grades (Abu Dawud, Tirmidhi, Nasa'i, Ibn Majah, Malik), they are kept as given and marked informational; they never make a hadith eligible (decision 17).

## Hadith: mhashim6 `Open-Hadith-Data`

- **What.** Musnad Ahmad and Sunan al-Darimi, the CSV files with diacritics, pinned to commit `1515f6cba21efed20d8916bf55acef1dffa0d2d5` and checked by SHA-256. The project took its files from the hadith-islamware repository.
- **Licence** (`data/cache/hadith/open-hadith-data/LICENSE`). The database is under the Open Database License 1.0 and its contents under the Database Contents License 1.0. The ODbL asks that a public use of the database, or of a work produced from it, carry a notice that credits the database and its licence (§4.3), and that a database derived from it and shared publicly be offered under the ODbL (§4.4).
- **Inside the app.** Showing these hadiths is a public use of a produced work: `/sources` carries the project's notice verbatim, below.
- **In the corpus archive.** The archive is a derived database shared publicly: `NOTICE.txt` states that the rows of these two books, with their search copies, are shared under the ODbL and carries the notice. The ODbL covers those rows only; the rest of the archive keeps its own terms (a collective database).
- **Notice**, as the project states it:

  > This Open-Hadith-Data project is made available under the Open Database License: <http://opendatacommons.org/licenses/odbl/1.0/>. Any rights in individual contents of the database are licensed under the Database Contents License: <http://opendatacommons.org/licenses/dbcl/1.0/>

## Hadith rulings: dorar.net

dorar.net («الدرر السنية») is never called from the server: it blocks automated access (decision 18). An editor opens it in a browser and records the ruling exactly as dorar gives it, with the scholar, the book and page and the address of the dorar page; the app shows that address with the ruling. Every hadith also carries a dorar.net search link for the reader («تحقق في الدرر»). A ruling is a short quotation with its source and a link; dorar's own terms for quoting have still not been reviewed.

## Places: GeoNames

- **What.** `allCountries`, `alternateNamesV2`, `hierarchy` and `countryInfo` from `https://download.geonames.org/export/dump/`, loaded into the `geodata` schema (`scripts/geodata/ensure.sh`), either fresh or from the owners' dump of 2026-10-04.
- **Licence.** Creative Commons Attribution 4.0. It requires credit to GeoNames, a link to the licence, and saying whether the data was changed.
- **Inside the app.** The atlas map's credit line names GeoNames with a link; `/sources` credits it with the licence link and says the data is stored, selected and indexed by us. Place searches never leave our servers (privacy policy).
- **In the bucket.** The dump is a redistribution: `geodata/NOTICE.txt` beside it gives the source, the licence link and the changes.

## Map: OpenStreetMap, OpenFreeMap, OpenMapTiles, MapLibre

The atlas map loads its tiles from OpenFreeMap (decision 9), which builds them from OpenStreetMap data on the OpenMapTiles schema. OpenStreetMap data is under the ODbL, which requires «© OpenStreetMap contributors» or «© OpenStreetMap» with a link to `https://www.openstreetmap.org/copyright`, visible on the map; OpenFreeMap and OpenMapTiles ask for their own credit. The map's credit line (`apps/web/src/components/atlas/map-view.tsx`) shows OpenFreeMap, © OpenMapTiles, © OpenStreetMap and GeoNames, each linked, and a link to `/sources`. MapLibre GL JS is BSD-3-Clause; its licence ships in the package.

## Object detection: Ultralytics

`services/vision` runs YOLOE through the `ultralytics` package, under the GNU AGPL 3.0, so the whole repository is AGPL-3.0 (`AGENTS.md`). The repository has a root `LICENSE` with the AGPL text (as `services/vision/LICENSE` already had), and the root `package.json` says `AGPL-3.0-only`. AGPL §13 asks that people who use the program over a network be offered its source: `/sources` links to `https://github.com/IslamWonder/tabsira`. The detector weights are downloaded by `services/vision/scripts/fetch-weights.sh` under the same licence and are not committed.

## Fonts

Readex Pro, Reem Kufi and Noto Naskh Arabic, from the `@fontsource` packages, under the SIL Open Font License 1.1, which allows embedding and self-hosting with no notice on the page. They are named on `/sources` all the same.

## Retrieval aids, never displayed as scripture

- **Annotated Quran corpus** (`final_complete_verses_20251202_194512.json`, Firas Ben Sassi). The project's own: annotations written by gpt-4o-mini, used to find verses. Its verse text (Tanzil-derived) is not stored: it is read only to leave out the annotation strings that repeat the verse (514 of them). Its English translation (source and licence unknown) is not imported.
- **Enriched Sunnah file** (`processed_sunnah_data.json`). The project's own enrichment, written by gpt-5-mini, of a hadith compilation that is not identified. Its fields are ranking signals; its abridged narrations are not stored, and its summaries and paraphrases are stored as model-written and never shown as hadith.
- **World ontology and learning path.** Written by the TABSIRA team.
- **Scripture vectors.** Computed by us with the AI provider's embedding model; the archive holds vectors, references and text hashes, no text (`vectors/NOTICE.txt`).

## Tools used to build TABSIRA

The contest asks for a register of the tools used, beside the sources. None of these tools wrote or chose a Quran or hadith text: scripture always comes from the sources above, by id.

| Tool                             | Used for                                                                                                                           | Terms                                                                    |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| ChatGPT (OpenAI)                 | Generating images of the project                                                                                                   | OpenAI's terms of use: the output belongs to the user                    |
| Magnific (Freepik, Flaticon)     | The interface icons (the Good Ware Lineal family) and the landing picture, `docs/ASSET_MANIFEST.md`                                | Magnific premium licence of the owners' account; no attribution required |
| Freepik text-to-image            | The generated photos of the gold scenes of `make eval` (`apps/api/tests/evaluation/scenes/gold.json`, provenance of each)          | Freepik's terms for the owners' account                                  |
| Claude Code (Anthropic)          | An assistant for writing the code, the tests and the documents, under the owners' direction and review                             | Anthropic's terms: the output belongs to the user                        |
| OpenAI and OVHcloud AI Endpoints | The models the running app calls: scene analysis, search vectors, verification, the explanation and the chat (`docs/BENCHMARK.md`) | Each provider's terms; what is sent is in the privacy text (`/privacy`)  |

## Not used

HadeethEnc (decision 19). Tanzil and alquran.cloud were read for the audit only (`docs/ASSET_MANIFEST.md` §2).

## Still open

- dorar.net's terms for quoting rulings: not reviewed.
- The provenance of the Arabic text of `hadith-api` is not documented by the project.
