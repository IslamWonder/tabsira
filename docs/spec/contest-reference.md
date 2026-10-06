# The contest's reference pack

«المرجعية والحزمة العلمية والبيانات», version 20/3/1448, the scientific requirements published before the challenge «تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي».

- **Address:** <https://islamicaich.org/files/HackathonFile/ZA1IoQnh5S1tuLFiBghyT7U2HYN6IpzNDg9vamHW.pdf>
- **Copy read on 2026-10-06:** 15 pages, SHA-256 `446911252f2012d36afe52db3e9afaf0dae52615da34e134aa4e95a199cd65bf` (kept in `../tabsira-artifact/contest/`, never committed).

This page summarises what binds TABSIRA. The pack wins over our own reading of it; where a rule here and a decision in `DECISIONS.md` disagree, the owners decide and the decision is written down.

## Approved sources, by field

| Field                   | Approved content                                                                                                                     | Rule of use                                                       | TABSIRA                                                                                                                                        |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Quran                   | The Quran text in its approved script and text, the King Fahd Complex print or quranpedia.net                                       | Make sure verses are transmitted reliably                         | Displayed text: quranpedia mushaf 2 (decision 16). A copy in today's spelling for the leak guard is our own processing of that text (task 05.9) |
| Tafsir                  | Any Islamic source of the first three centuries, or dorar.net/tafseer                                                                 | Explain a verse while keeping the commentator's words apart       | Not used: the explanation is generated and labelled as such; fetching tafsir is deferred (v2 §28)                                             |
| Hadith                  | The sahih hadiths of the two Sahihs; another book's hadith only once its soundness is checked (dorar.net/hadith or shamela.ws editions) | **No hadith is attributed without a source and an approved ruling in the data** | Nine books with their graders' grades; see the gap below                                                                                       |
| Creed, fiqh, sira       | Early sources or dorar.net (aqeeda, feqhia, history)                                                                                  | No personal fatwa, no automatic preference                         | Out of scope: the chat refers level (d) questions                                                                                             |
| Frequent questions      | «بينات» (dawa.center/file/7937)                                                                                                       | Main source for dialogue answers                                  | Not used                                                                                                                                       |
| Terms and translation   | islamic-content.com/dictionary                                                                                                        | Preferred over machine translation for sensitive terms            | Arabic only                                                                                                                                    |

The pack also lists, as recommended references, the association's platforms (quranenc.com, hadeethenc.com, byenah.com, islamhouse.com, islamenc.com, terminologyenc.com, icadb.com, an MCP server at mcp.islamiccontent.org), risala.prh.gov.sa, tafsir.net, mp3quran.net, the Kuwaiti fiqh encyclopedia, islamqa.info, binbaz.org.sa, binothaimeen.net, the King Salman academy's dictionaries, the King Fahd Complex (fonts, translations, the mushaf text for developers in XML and JSON with verse and word ids), dorar.net (a hadith search with a JSON interface) and shamela.ws. Tanzil is not among them.

## Binding standard for every output

1. **Reliability and attribution.** Every religious statement, quotation or ruling can be traced to its source; no text or saying is attributed to a reference that does not contain it; scripture is kept apart from generated explanation; the app says when the information is not enough.
2. **Certain versus disputed.** Disputed questions are never stated as certain; the dispute is mentioned as far as the context needs.
3. **No independent fatwa.** Refer, or ask for clarification, when facts or a scholar's judgement are needed.
4. **Against hallucination.** Without enough reference or confidence: abstain, hedge or refer, never an undocumented answer.
5. **Da'wah quality.** The listener's background, level, language and context; the root before the branch; correct and clear.
6. **Translation.** Keep the religious meaning of a term.
7. **Transparency.** Say it is an AI-assisted tool when the user might think a scholar answers.
8. **Privacy.** Collect only what is needed, under a published policy; draw no unnecessary religious conclusions about the user.

Content levels (a) to (d) and the twelve test questions are the ones already in `master-prompt-v2.md` and `docs/EVALUATION.md` («The twelve chat cases»).

## Where TABSIRA stands (2026-10-06)

- **Met:** displayed Quran from quranpedia; scripture loaded by id and never written by a model; levels (a)–(d) and referral in the chat; the twelve cases (12/12 in `make eval` of 2026-10-06); the AI disclosure («تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا»), the explanation labelled as AI-assisted reflection apart from the texts; the privacy rules.
- **Not a gap, a quality note:** the «وجه الصلة» line under «لماذا ظهر هذا؟» is part of the generated explanation, which the app labels as AI-assisted reflection apart from the texts, as rule 1 asks; rule 1's «ألا ينسب نص أو قول إلى مرجع لا يوجد فيه» is about quoting or attributing a text, which the line does not do. The line is the search query, and the mock audit found some that misdescribe the text; the owners kept it (2026-10-06). Task 05.10, optional.
- **Gap, hadith admissibility:** decision 65 shows a hadith with no ruling yet, and `app.hadith_rulings` is empty, so three hadiths that every grader in the corpus calls weak were shown in the mock data. The pack asks for a source and an approved ruling, and the two Sahihs or a checked hadith. Task 05.11.
- **Changed, Quran guard source:** Tanzil's text was proposed for the guard and dropped, since it is not an approved source; the guard uses our own processing of the quranpedia text (task 05.9).
