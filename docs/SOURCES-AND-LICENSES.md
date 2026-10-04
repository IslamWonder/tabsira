# Sources and licences

What the scripture store and its retrieval aids are built from, under which terms, and the credit each source asks for. Versions, file hashes and counts are in `docs/ASSET_MANIFEST.md`; the owners' choices are decisions 16 to 19 in `docs/spec/DECISIONS.md`.

| Source                                   | Used for                                | Licence                                                   | Credit we give                                              |
| ---------------------------------------- | --------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------- |
| quranpedia.net, «مصحف حفص نسخة نصية»     | Displayed Quran text, daily corrections | quranpedia data licence (2026-10-01)                      | «الموسوعة القرآنية — quranpedia.net», a link on every verse |
| KFGQPC Uthmanic Script Hafs v22          | Quran font (not yet added)              | King Fahd Complex terms, to be checked                    | The Complex, once the terms are read                        |
| fawazahmed0 `hadith-api`                 | Seven hadith books                      | Unlicense                                                 | Named on the sources page                                   |
| mhashim6 `Open-Hadith-Data`              | Musnad Ahmad, Sunan al-Darimi           | ODbL 1.0 and DbCL 1.0                                     | The notice below, on the sources page                       |
| dorar.net                                | Hadith rulings, recorded by editors     | dorar's terms (not yet reviewed)                          | The dorar page of each ruling                               |
| Annotated Quran corpus (Firas Ben Sassi) | Retrieval signals for verses            | The project's own                                         | —                                                           |
| Enriched Sunnah file                     | Retrieval signals for hadiths           | The project's own; its source compilation is unidentified | —                                                           |

## Quran text: quranpedia.net

- **What.** Mushaf 2, «مصحف حفص نسخة نصية»: the King Fahd Complex Uthmani text of Hafs as quranpedia publishes it, from its official versioned dumps (`https://api.quranpedia.net/dumps`), each file checked against the SHA-256 of the dump manifest. Corrections come from its changes feed (`/v1/changes`), applied daily by `src.cli.sync_quran`.
- **Licence** (`LICENSE.md` of the dumps, version 2026-10-01). The Quran text is the shared heritage of the ummah; the digitisation, structuring, verification, diacritical correction and metadata are the work of the quranpedia team. Use inside apps and websites is free and needs no attribution (a link is appreciated). Republishing the data itself, whole or in part, as a downloadable database or dataset requires crediting quranpedia.net with a link and stating the dump version. Copies must be kept current through the changes feed; the data comes without warranty.
- **Our use.** Inside the app only; the store is not republished as a dataset. Every verse links to its quranpedia page (`https://quranpedia.net/surah/2/{surah}#verse-{id}`), and the sources page credits «الموسوعة القرآنية — quranpedia.net» with the dump version in use.
- **Usage policy** (`https://quranpedia.net/api-docs#usage-policy`). Dumps rather than crawling the API, the changes feed to stay current, at most 120 requests a minute. The importer makes three requests per run, the sync one plus one per corrected verse, spaced 0.6 s apart, with `User-Agent: tabsira/0.1 (+https://tabsira.me)`.
- **Not used.** The dumps also carry word morphology (Quranic Arabic Corpus, GNU GPL) and i'rab syntax (The Quranic Treebank, MIT); those files are not downloaded.

## Quran font: KFGQPC Uthmanic Script Hafs v22

quranpedia renders mushaf 2 with `UthmanicHafs_V22.ttf`, made by the King Fahd Glorious Quran Printing Complex; decision 16 asks for it self-hosted. It has not been downloaded or committed yet. Its redistribution terms have to be read from the Complex's own distribution before it is served from our domain.

## Hadith: fawazahmed0 `hadith-api`

- **What.** The Arabic editions of al-Bukhari, Muslim, Abu Dawud, al-Tirmidhi, al-Nasa'i, Ibn Majah and Malik, pinned to commit `df57907be35291c91ad6a6691180e22ca9920784` and checked by SHA-256.
- **Licence.** The Unlicense: a dedication to the public domain; no condition. The editions name no source and give "Unknown" as the author of the Arabic text, so its provenance is not documented.
- **Grades.** Where the dataset has grades (Abu Dawud, Tirmidhi, Nasa'i, Ibn Majah, Malik), they are kept as given and marked informational; they never make a hadith eligible (decision 17).

## Hadith: mhashim6 `Open-Hadith-Data`

- **What.** Musnad Ahmad and Sunan al-Darimi, the CSV files with diacritics, pinned to commit `1515f6cba21efed20d8916bf55acef1dffa0d2d5` and checked by SHA-256. The project took its files from the hadith-islamware repository.
- **Licence.** The database is under the Open Database License 1.0 and its contents under the Database Contents License 1.0. The ODbL asks that a public use of the database, or of a work produced from it, credit the database and its licence, and that a database derived from it and shared publicly be offered under the ODbL as well. The store keeps these two books as given, with hashes and search copies; it is not shared as a dataset.
- **Notice** for the sources page, as the project states it:

  > This Open-Hadith-Data project is made available under the Open Database License: <http://opendatacommons.org/licenses/odbl/1.0/>. Any rights in individual contents of the database are licensed under the Database Contents License: <http://opendatacommons.org/licenses/dbcl/1.0/>

## Hadith rulings: dorar.net

dorar.net («الدرر السنية») is never called from the server: it blocks automated access (decision 18). An editor opens it in a browser and records the ruling exactly as dorar gives it, with the scholar, the book and page and the address of the dorar page; the API shows that address with the ruling. Every hadith also carries a dorar.net search link for the reader («تحقق في الدرر»). dorar's terms for quoting its rulings have not been reviewed yet.

## Retrieval aids, never displayed as scripture

- **Annotated Quran corpus** (`final_complete_verses_20251202_194512.json`, Firas Ben Sassi). The project's own: annotations written by gpt-4o-mini, used to find verses. Its verse text (Tanzil-derived) and its English translation (source and licence unknown) are not imported.
- **Enriched Sunnah file** (`processed_sunnah_data.json`). The project's own enrichment, written by gpt-5-mini, of a hadith compilation that is not identified. Its fields are ranking signals; its abridged narrations are not stored, and its summaries and paraphrases are stored as model-written and never shown as hadith.

## Not used

HadeethEnc (decision 19). Tanzil and alquran.cloud were read for the audit only (`docs/ASSET_MANIFEST.md` §2).
