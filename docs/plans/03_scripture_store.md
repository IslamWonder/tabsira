# 03 · Quran and hadith sources

**Phase:** 1 · **Priority:** Critical · **Status:** ✅ · **Updated:** 2026-10-04 14:51 (Tunis)

Every verse and hadith shown comes from a verified store, byte for byte, never from a model. Hadith grades are recorded by editors from dorar.net.

| Step                                                      | Status | Notes                                                            |
| --------------------------------------------------------- | ------ | ---------------------------------------------------------------- |
| Quran: 6,236 verses, verified, with daily corrections     | ✅     |                                                                  |
| Hadith: nine books, 65,712 hadith                         | ✅     |                                                                  |
| Editor rulings (grades) with a «تحقق في الدرر» link       | ✅     | Recorded from the command line for now.                          |
| Guard: model text may not copy any stored verse or hadith | 🔄     | Strengthened in the scan workflow review (quotes across verses). |
| Rulings screen for editors                                | ⏸      | With the later admin work.                                       |
| Reference data from the owners' bucket                    | ✅     | 03.4: `corpus` schema, verified archive, GeoNames dump.          |

**Waiting on the owners**

- Rulings for the rain-scene hadith Bukhari 1032 and 2320 (owners).

**How we check it**

- Displayed text compared with its stored fingerprint in tests.
- Scripture review before every merge that touches it.

## Tasks

### 03.1 Record the rain-scene hadith rulings

- **Status:** ⏸ waiting on owners
- **Goal:** Editors record dorar.net grades for Bukhari 1032 and 2320 so the tutorial can show them.
- **Depends on:** The owners' rulings.
- **Touches:** Data only, through `python -m src.cli.record_ruling`.
- **Done when:** The tutorial shows both hadith with their grade.

### 03.4 Reference data from the owners' bucket

- **Status:** ✅ 2026-10-04 23:05
- **Goal:** The scripture store, the world ontology and the learning path live in a `corpus` schema and install from a verified archive in the owners' bucket; GeoNames from a dump in the same bucket or, on request, from geonames.org (decision 57).
- **Touches:** `apps/api/src/models/{base,scripture,ontology,learning}.py`, the app migration `20261004_209000`, the vectors migration's keys, `scripts/{corpus,geodata}/`, `scripts/data.sh`, `scripts/data.ps1`, `scripts/vectors/`, `deploy/load-data.sh`, the search path in the setup and provisioning scripts, `docs/CORPUS.md`.
- **Done when:** `make data` installs GeoNames (when configured), the corpus and the vectors once each from verified files, and the archive of the development database is exported for the owners to upload.
