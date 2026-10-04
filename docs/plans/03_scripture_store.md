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
