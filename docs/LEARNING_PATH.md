# Learning path («مسار»): how the data is built

`docs/spec/masar.md` is the reference for the learning path. It is never edited by code, and `DECISIONS.md` wins where they disagree. This file records how the reference becomes data, and the **implementation decisions** taken where the reference is silent or can be read in two ways. Those decisions are ours: they are not text from `masar.md`, and each one can be revisited by the owners.

## From the document to the database

```text
docs/spec/masar.md
  └─ parse_masar ──► data/masar/tabsira-masar-1.0.json   (generated, committed)
                       └─ validate_masar ──► import_masar ──► app.learning_*
```

| Step     | Command (from `apps/api`)                                            | What it does                                                                                    |
| -------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Parse    | `uv run python -m src.cli.parse_masar`                               | Reads the Markdown, writes the versioned JSON. `--check` fails when the JSON is out of date.    |
| Validate | `uv run python -m src.cli.validate_masar FILE`                       | Counts, ids, orders, prerequisites (they exist, no cycle), depths, coverage, evidence pointers. |
| Import   | `uv run python -m src.cli.import_masar [--activate]`                 | Validates, then loads one version into the database in one transaction.                         |
| All      | `bash scripts/data-learning.sh` (`data.sh` calls it for `make data`) | The importers of the ontology and of the path, with the counts the first release must hold.     |

Version 1.0 holds **16 domains and 96 units** (`T00` to `T15`, six units each) and six depths `L0` to `L5`. The importer and the validator check the counts a file declares against what it holds; only the 1.0 commands pass `--expect-domains 16 --expect-units 96`, because a later release has other counts.

## Versions and monthly releases

The path is data, not code (master prompt v2, section 13). Every table row carries its `path_version`:

- `app.learning_path_versions`: one row per release, with the hash of the imported file, the depths, the coverage rules and an `is_active` flag. At most one row is active (a partial unique index).
- `app.learning_domains` and `app.learning_units`: keyed by `(path_version, id)`.
- A monthly release is a new file `data/masar/tabsira-masar-<n>.json` of the same shape, imported with `import_masar`. Nothing in the code changes.
- Importing the same file again changes nothing. Another file for a version already published is refused: a published version does not change. `--replace` exists for the time before a release is published, and is refused while a learner has state for a unit that the new file drops.
- A first version becomes active by itself; a later one waits for `--activate`.

The parser is for the Markdown of `masar.md`. A later release can be written directly in the JSON shape (`src/schemas/learning_path.py`), and the validator holds it to the same rules.

## Decisions

### Names and identifiers

- **D1. Path version `tabsira-masar-1.0`.** The file calls itself `tabsirah-masar-1.0` (with an h); master prompt v2, section 29, says the name has no h and the identifier is `tabsira-masar-1.0`. The file's own identifier is kept in `source.reference_id`.
- **D2. Ids are the document's ids** (`T00`, `T00_01`). They are never regenerated, and never reused for another meaning.
- **D3. Order.** A domain's `order` is its place in the map of section 4, starting at 1 (so `T00` is 1). A unit's `order` is its place in its domain, 1 to 6, and must match its id.

### What the document does not state

- **D4. A unit has no title in the document.** Section 5 says a unit id is stable and "is not replaced by a title the machine generates". So `title` is the objective sentence exactly as written, and `objectives` holds that one sentence. A later release can give a unit a real title and several objectives.
- **D5. Depths.** Section 3.2 defines the six depths once, for every unit; it gives no depth for a particular unit and no teaching material per depth (the contract of section 14 has `depthMaterials`, which the tables do not fill). So the file defines the depths once (`depths`) and each unit lists all six as the depths it can be learnt at. Material per depth, its review status and the search terms of a unit are editorial content for a later release; the importer does not invent them.
- **D6. Concepts.** Section 4 gives the central concepts of a **domain**; they are kept on the domain. A **unit** has concepts only where section 7 states a search vocabulary for it, which it does for two units: `T08_03` («التثبت، خبر، نقل، تحقق») and `T12_02` («إنبات»، «غرس الإنسان»، «الانتفاع بالغرس»). Those two are read from the document and checked against it on every parse. No other unit inherits its domain's concepts: that would make a phone in a scene match the whole of `T08`.

### Evidence references

- **D7. Text pointers only.** `evidence_refs` holds each reference as the document writes it (for example `الإسراء 36`, or `مسلم 8a`), never the text of a verse or a hadith. The validator refuses a "reference" longer than 120 characters or carrying the marks or the ornate brackets of Quranic text.
- **D8. Anchors.** `source_anchors` gives each pointer a stable form: `Q:17:36`, `Q:3:190-191`, `Q:112` for a whole surah, `H:bukhari:2320`, `H:muslim:8a`. They are read from the links of the document, and from a plain mention of a reference that a link elsewhere in the document spells out. One link uses a slug (`quran.com/al-baqarah/2`); `SURAH_NUMBER_BY_SLUG` in the parser maps it, and another slug fails the parse until it is added there. Three units (`T15_02`, `T15_05`, `T15_06`) point at "the sources of other units" and have no anchor.
- **D9. Links are reading pointers.** The `quran.com` and `sunnah.com` links of the document are used only to build anchors. They are not stored as addresses and they do not decide what is shown: the displayed source is quranpedia and dorar (master prompt v2, section 29).

### Prerequisites and coverage

- **D10. «لا شيء» is an empty list.** A prerequisite is knowledge to prepare before going deeper, never a lock (section 3.3). The validator requires every prerequisite to be a unit of the same file, none to point at itself, and no cycle; it is not an order of display.
- **D11. Coverage rules** come from the table of section 6, with their references as written (`T02`, `T04_02 إلى T04_04`, `T07 إلى T12`) and the units they expand to. The validator checks that they point at units that exist. They steer the choice towards a domain that is less present; they are not a gate (section 10.4, criterion 7).

### What is not imported

- **D12. Not data.** The scene examples of section 7, the rules of sections 8 to 16 (adapting the speech, what counts as evidence, the selection algorithm, the examples of decisions, the acceptance cases) describe how the engine behaves; they are not rows. The selection algorithm of section 10 is the planner's job and is not built here; these tables hold what it will read (units, prerequisites, depths, coverage, and the learner's state).
- **D13. The strict shape.** A file with a field the schema does not know is refused, so a typo does not pass silently. A release that needs a new field changes the schema with that release.

### Reproducibility

- **D14. The JSON has no timestamp.** The same document gives the same bytes, so `git diff` shows a change only when the document changed, and a test fails when `masar.md` is edited without regenerating the data. The hash recorded in `source.sha256` is that of the document with LF line endings.

## The learner's state

`app.learner_unit_states` has one row for a learner and a unit of a path version, once something happened (no row means "not seen"):

- **Owner.** An account (`user_id`) or a guest (`guest_key`, an opaque key of at least 16 characters held by the browser), never both and never neither. Each owner has at most one row per unit of a version. A guest's rows are merged into the account at the first sign-in, by the route that does it.
- **Counts.** `seen_count`, `opened_count` and `completed_count`, with `last_at`.
- **`completed_count` is completion, never mastery.** It counts the times the learner pressed «تمّ» on an insight of that unit. It does not say the learner understood anything, and it is never turned into a score, a level or a percentage (master prompt v2, rules 9 and 13). What the learner understood is evidence of another kind (section 9.2 of the reference) and is recorded elsewhere, from answers, when the routes exist. The database says so in the comment of the column.
- **The unit is named with its version.** When a unit's meaning changes it is a new unit or a new version, and old evidence is not carried over (section 14 of the reference, rule 7). A state keeps its unit: a unit with learner state cannot be deleted from under it.
- **Accounts.** `user_id` has no foreign key yet because the accounts tables are created by another change. When they are in the same chain it gets `REFERENCES app.users (id) ON DELETE CASCADE`, so deleting an account deletes its learning state (master prompt v2, section 15).

There are no routes yet, and no deletion of the learning record from the screen; those come with the account and profile routes.
