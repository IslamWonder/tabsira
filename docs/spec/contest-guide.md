# The participant's guide

«دليل المشارك — تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي», Bathel Foundation (مؤسسة باذل الأهلية), 2026: how the challenge runs, what must be delivered and how it is judged. The approved sources and the binding standard for outputs are in the other document, [contest-reference.md](contest-reference.md).

- **Address:** <https://islamicaich.org/files/HackathonFile/da2OrbRMEsNrIQaoq8z6jEv26opKXdQmq1i0XfXo.pdf>
- **Copy read on 2026-10-06:** 44 pages, SHA-256 `7dcf525b7fbdee92b0eda80432ec03c9794614031e3584dcf5012977e5488994` (kept in `../tabsira-artifact/contest/`, never committed).
- **Contact:** info@IslamicAIch.org; <https://IslamicAIch.org/contact-us>. Registration files and sensitive data never go through Discord.

## Dates (Riyadh time, UTC+3)

| When                          | What                                                                                               |
| ----------------------------- | -------------------------------------------------------------------------------------------------- |
| 4–6 October, 09:00 each day   | Challenge days, remote; mentoring 10:00–19:00                                                       |
| **6 October 2026, 23:59**     | **Submission and every change to it close** (open since 4 October 09:00), through the portal; keep the confirmation message |
| 7–15 October                  | First judging on the portal: up to 20 projects shortlisted                                          |
| 18 October                    | Finalists announced                                                                                 |
| 19–22 October                 | Final judging on Zoom: 8 minutes a team (5 to present, 3 for questions), up to 5 winners           |
| 26 October                    | Closing ceremony in Riyadh (optional to attend); prizes 200,000 SAR for 5 places                    |

A submission problem caused by a general outage is reported to info@IslamicAIch.org with proof of the attempt and the participation number.

## What must be delivered

| Deliverable                                                                                                   | Where TABSIRA stands                                                                                           |
| ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| A complete product that works end to end, not a prototype, ready for real use                                  | The app; the first production deploy is task 14.1 (rehearsed in containers, real servers pending)              |
| A live link that works fully, tested before submitting                                                         | <https://tabsira.me> once deployed; `make smoke` against it                                                    |
| A **public** GitHub repository (a private one is refused): the code the team may publish, run instructions, licences, no secrets, passwords or users' data | `README.md`, `docs/SETUP.md`, `docs/OPERATIONS.md`; making it public is the owners' step; the licence of the rest of the repository is still the owners' choice (decision 5) |
| Documentation of the idea, setup, running, credits, and a register of sources, tools and licences              | `docs/SOURCES-AND-LICENSES.md`, `docs/ASSET_MANIFEST.md`, `docs/CORPUS.md`                                     |
| Documentation of the religious and knowledge sources: how they are used and checked                            | `docs/SOURCES-AND-LICENSES.md`, `docs/CORPUS.md`, `docs/EVALUATION.md`, [contest-reference.md](contest-reference.md) |
| A presentation (PDF or PowerPoint, Arabic or English): the problem, the solution, how it works, the added value, the technologies in detail, screenshots, results, the plan to continue | Not in the repository (the owners)                                                                            |
| A video of at most two minutes                                                                                 | Not in the repository (the owners)                                                                            |

A project started before the challenge is allowed when its starting version is documented and its rights disclosed; only what was done from 4 to 6 October is judged. The starting point is «the earlier prototype» (AGENTS.md); `docs/CHALLENGE-LOG.md` records the work of the challenge days.

## Tracks

1. Knowledge dialogue and reliable answers.
2. Multilingual content and cultural localisation.
3. Interactive experiences and the learning journey to know and learn Islam: success is a better understanding of an Islamic concept for the target group, a fitting sequence and a continuous journey, **with privacy and without inferring or classifying the user's religious or sensitive traits without a legitimate basis**.
4. Knowledge and verification tools for those who introduce Islam.
5. Open track.

TABSIRA's track is the one the owners registered; its success criterion carries 20 % of the final mark.

## Final judging (stage two)

| Weight | Criterion                                                                                                                           |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 25 %   | Technical quality and use of AI: stable product, AI doing a real job with a clear method; top mark for results repeated stably, documented method and limits |
| 20 %   | Benefit by the track's success criterion: a measured improvement for the target group, compared with a baseline                       |
| 15 %   | Reliability and scientific soundness: sources, attribution, abstaining and referral in the required cases; top mark for consistent results over the whole test set across repeated runs, with known limits and errors traced |
| 15 %   | Innovation and added value against a named alternative, shown by a test                                                              |
| 10 %   | User experience, communication and accessibility                                                                                   |
| 10 %   | Realistic operation after the challenge: costs, dependencies, content review, maintenance                                            |
| 5 %    | Clarity of the presentation and how easily the claims can be checked; what is done kept apart from what is proposed                 |

The first-stage selection score is not carried into the final result.
