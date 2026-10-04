# Fonts

Every face is served by the web app itself; the visitor's browser never asks Google Fonts or any CDN for one (AGENTS.md, master prompt §25). `index.ts` declares them with `next/font/local`, `display: swap`, and only the weights the interface uses.

| Use                            | Face                                     | Weights                                                                       | Source                                | Licence                                                              |
| ------------------------------ | ---------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------- | -------------------------------------------------------------------- |
| Display headings, 24 px and up | Reem Kufi                                | 700 (Arabic)                                                                  | `@fontsource/reem-kufi` 5.3.0         | SIL Open Font License 1.1, © 2015–2022 The Reem Kufi Project Authors |
| Interface                      | Readex Pro                               | 400, 500, 600 (Arabic); 400, 600 (Latin, loaded only when Latin text appears) | `@fontsource/readex-pro` 5.3.0        | SIL Open Font License 1.1, © 2019 The Readex Pro Project Authors     |
| Hadith                         | Noto Naskh Arabic                        | 400, 700 (Arabic)                                                             | `@fontsource/noto-naskh-arabic` 5.3.0 | SIL Open Font License 1.1, © 2022 The Noto Project Authors           |
| Ornate brackets ﴿ ﴾ only       | Amiri                                    | 400 (Arabic), restricted to U+FD3E–FD3F                                       | `@fontsource/amiri` 5.3.0             | SIL Open Font License 1.1, © 2010–2022 The Amiri Project Authors     |
| Quran                          | KFGQPC HAFS Uthmanic Script, version 2.2 | 400                                                                           | `UthmanicHafs_V22.ttf` in this folder | King Fahd Glorious Quran Printing Complex end-user licence, below    |

The four OFL faces are read straight from the pinned `@fontsource` packages in `node_modules`, so their full licence travels with each package (`node_modules/@fontsource/*/LICENSE`) and no copy is kept here. `next/font/local` copies the files into the build unchanged.

## KFGQPC HAFS Uthmanic Script (`UthmanicHafs_V22.ttf`)

- **Source:** <https://quranpedia.net/assets/fonts/arabic/UthmanicHafs_V22.ttf>, the font quranpedia.net serves with its Uthmani Hafs text (owner decision 16 in `docs/spec/DECISIONS.md`). Downloaded on 4 October 2026; the server reported it last modified on 14 September 2026.
- **File:** 297 700 bytes, SHA-256 `aa68bffce289b4c0ebac68e90502eb69e42356abcd1603cb2b8e99c2c723f145`. Its name table reads «KFGQPC HAFS Uthmanic Script», version 2.2, © 2010 King Fahd Glorious Quran Printing Complex, <http://fonts.qurancomplex.gov.sa/>.
- **Licence:** the end-user licence embedded in the font (name ID 13) grants, free of cost, the rights to use, copy and distribute the font with its licence, on two conditions: it may not be sold, modified, altered, translated, reverse engineered, decompiled, disassembled or reproduced in any other way; and it is provided as is, without warranty. The licence travels inside the file itself.
- **What that means here:** the file is kept exactly as downloaded. It is not subset, not converted to WOFF2 and not renamed by any tool; `next/font/local` serves a byte-identical copy under a hashed name. To update it, download the new version from the same source, replace the file, and update the size, the hash and the version above in the same commit.
