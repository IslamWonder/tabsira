# What changed between the first prompt and v2, and why

Three inputs were merged into `tabsira_master_prompt_v2.md`:

- **v1** — `tabsira_master_prompt_updated.md` with its companions «مسار.md» and «تجربة.md».
- **Comments** — Ghazi's notes in `comments.md`.
- **Built** — the version developed before the contest (`the earlier prototype`): what worked, what broke, and what the contest files require.

Decisions taken on 2 October 2026 are marked **decided**. The code is rewritten from scratch when the contest starts; nothing here is code.

## 1. The big decisions

| Topic | v1 | Comments | Built | v2 |
|---|---|---|---|---|
| Starting point | Extend an existing repository | — | A working TypeScript monorepo | **Decided:** rewrite from scratch on 4 Oct. Only work of 4–6 Oct is judged |
| Stack | Next.js full-stack, Python for vision | Python backend, React + Tailwind | Next.js full-stack + Prisma | **Decided:** Next.js front end (pm2) + FastAPI back end (gunicorn) with all AI logic in Python |
| First screen | Profile questions, then camera; rain is an optional example | Suggest an account after the first Basira | Rain scene first | **Decided:** rain scene first as the tutorial; two more tutorial scenes on day 3 |
| AI provider | `gpt-5.4-mini` only (and `gpt-6.1-sol` named by mistake in three places) | Qwen on OVH, benchmark, one configuration array per provider | OVH Qwen with provider routing | **Decided:** both switchable; the benchmark picks the default |
| Social network | Full network: feed, follow, comments, moderation | Simplest possible, public Basira by id | Not built | **Decided:** public page by id plus share card. Full network after the contest |
| Photos | Optional storage | Unsure: consent and cost | Never stored | **Decided:** stored on S3 with the account owner's consent. Never for sensitive scenes, guests or under-13 |
| Re-shooting "through the last Basira" (lens) | Full new pipeline per lens shot | Rejected: complex and boring; proposes a hidden treasure | Two curated lenses | **Decided:** replaced by the hidden treasure (§17) |
| Scope order | One long list | We must be stable from day 1 | — | Three days with explicit scope; days 2–3 features behind flags |

## 2. Every comment, and where it went

| Comment | In v2 |
|---|---|
| Benchmark OpenAI against OVH; switchable provider | §22: one settings block per provider, `make benchmark`, the result sets the default |
| YOLO is good; take something better if it exists | §6: detector behind one interface (`yolo_world`, `vlm`, `grounding_dino`), chosen by benchmark and licence. Ultralytics is AGPL-3.0, which matters for a public repository |
| PWA so mobile needs no extra effort | §20, §21: PWA is the only client during the contest |
| Why do we need `cross_encoder_reranker.py`? | §9, and the explanation in section 3 below |
| Fix Arabic typos and expressions | v2 is rewritten in corrected Arabic; the product name is TABSIRA without "h" |
| Three design choices, never continue without a choice | §20: a blocking design gate, recorded in `docs/DESIGN_DECISION.md` |
| Understanding based on evidence only | Rule 3 of §0, and the `observed / inferred / user_confirmed / unknown` statuses |
| Can the ontology file be improved as the AI learns? | §7: unresolved entities are logged as candidates; a human reviews and releases a new version. The file is never changed automatically |
| "No religious results": Islam has a view on everything, with flexibility | §8: five levels of relation, ending with the opposite meaning and a labelled general reminder. Abstention is the last resort, never a fabricated link |
| Suggest an account after the first Basira | §4 step 7, §15 |
| Three questions are enough, configurable in a range | §5: `PROFILE_QUESTIONS_MAX`, range 0–3 |
| Age as ranges, not names | §5: numeric ranges |
| Never ask for a birth date | §5, stated as a rule |
| Several goals; add curiosity? | §5: goals are multi-select and include «الفضول والاستكشاف». Curiosity is a valid entry goal: it maps to the first two domains of the path and makes no claim about belief |
| Quran and hadith kept letter by letter | Rule 2 of §0, §10, acceptance test 3 (hash comparison) |
| Not OpenAI by default | §22: the benchmark decides |
| Image description as context beside detection | §6 |
| Arabic ontology data, or generate more? | §7: Birzeit Arabic Ontology, Arabic WordNet, Wikidata Arabic labels as enrichment sources, licences checked first |
| An image with no clear meaning may have one through its opposite | §8 level `OPPOSITE` |
| Show other texts of equal weight when one was already shown | §11 |
| The learning path is hidden, like the unconscious | §13 |
| Hidden treasure instead of the lens. "What do you think?" | §17. It is the better idea: it reuses candidates that are already verified, needs no camera flow, and gives a reason to come back |
| Saved Basira has an id and can be public | §18 |
| Storing photos needs consent and costs | §19 |
| The examples are not very accurate | §29: the four tutorial texts are reviewed by a specialist against the two approved sources before use |
| Technical choices are open to discussion | §21 after the stack decision |
| Configuration may drift | §22: one typed settings object, validated at start, mirrored in `.env.example` |
| Jenkinsfile sending results to SonarQube | §23 |
| Latest dependency versions, checked online | §21, and `AGENTS.md` |
| 100 % unit coverage, front and back | §23 |
| Works with and without Docker | §24 |
| One shell script to provision and install | §24 |
| pm2 and gunicorn, zero downtime, one by one | §24 |
| Share the image and the result text to social media | §18 |
| Cloudy learning map revealed like a video game | §16 |
| The path should be extendable like a game updated every month | §13: units and regions are data, shipped as monthly content releases |
| Google sign-in (added 2 Oct) | §15 |
| Logo and favicon from a designer (added 2 Oct) | §20, §25 |

## 3. Why a cross-encoder reranker

The first search (keywords plus embeddings) is fast but rough: it scores the question and each text separately. A cross-encoder reads the question and one text together and gives a relevance score, so the best 20–30 candidates can be put in the right order.

In the built version this step was done by a large language model and took about 20 seconds, the slowest stage. A cross-encoder on a laptop CPU does the same job in a few seconds, so it is worth having.

The reference file does two things: a multilingual BERT cross-encoder (`amberoad/bert-multilingual-passage-reranking-msmarco`) and a boost from hadith metadata. v2 keeps the idea, compares that model with `BAAI/bge-reranker-v2-m3` and with a language-model rerank, and keeps the one that measures best.

## 4. Added from the built version

| Lesson | In v2 |
|---|---|
| Photo by camera, upload or pasted link, with a guarded server-side fetch | §4, §6 |
| Sensitive scenes: image never shown back, meaning still given | Rule 8, §6 |
| Vision-model boxes are pixels, not ratios | §6 |
| Joyful, mostly white interface; clear heading font; Quran in the Mushaf font | §20 |
| No hover motion; sound effects on events only, off by default, no background sound | §20 |
| Honest progress stages and honest states | Rule 10, §26 |
| Guest data merged into the account at first sign-in | §15 |
| Database down must not hang the first page | §24 |
| Terms page describing every real data flow | §19 |
| Robots, sitemap, metadata, share preview, icons | §25 |
| Smoke test, gold-scene evaluation, developer inspector | §23 |
| A scheduler must run in one process only | §24 |
| No gpt-oss models | Rule 12 |
| Product name TABSIRA, domain tabsira.me | Header |

## 5. Added from the contest files

- Scope, dates, the six deliverables and the judging weights (§1).
- The approved sources: `quranpedia.net` and `dorar.net/hadith`. v1 already chose them, which matches the official package.
- The four content levels and the referral rule for personal cases (§12).
- The AI disclosure line (§12).
- The twelve official test cases as acceptance tests (§27).
- Evidence the rubric asks for: benchmark, evaluation report, user test, operations note (§23, §30).

## 6. Removed or postponed, with the reason

| Item in v1 | Status | Reason |
|---|---|---|
| Full social network | After the contest | Two people, three days |
| Panorama of the original photo | After the contest | Large effort, not needed for the core journey |
| Explanation RAG from tafsir and da'wah sites | After the contest | Needs ingestion rights and review; the explanation uses the verified pair and the path's edited material |
| Lens | Replaced | Hidden treasure |
| Profile questions before the first use | Moved | After the first Basira, three at most |
| Religion and gender among the first questions | Moved to settings | The goal «التعرّف إلى الإسلام» gives the same adaptation with less sensitive data, which the track criterion rewards |
| "The world spot appears only after the action" (UX file) | Changed | The Basira is saved on «تمّ»; the action is a separate state |
| Arabic file names in the repository | Changed | ASCII names in `data/`; Arabic names break tooling across Windows, Linux and macOS |
| Model name `gpt-6.1-sol` | Removed | It contradicted the named model |
| `processed_sunnah_data.json` as the hadith corpus | Changed | It holds 3,920 hadith with model-written rephrasing. It becomes ranking signals only; displayed text comes from the full corpus |

## 7. Still open

1. The Quran corpus file named in v1 is not in the shared folder.
2. The design file «d» never arrived; the design gate replaces it.
3. Which specialist reviews the tutorial texts.
4. The benchmark result (provider, detector, reranker).
5. Whether the public repository uses AGPL because of the detector.
6. Access method to quranpedia.net and dorar.net: ask the organisers for an export or API.

## 8. One risk to keep in view

The built version took several days and still had a 30–45 second analysis. A rewrite must reach a smaller core by Sunday evening. The day-1 milestone is cut to that core on purpose: no account, no chat, no world. If day 1 slips, drop day-3 features, never the day-1 checks.
