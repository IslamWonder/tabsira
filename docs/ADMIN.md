# The admin area

Decision 14 in one page: what the admin is, how someone gets in, what it shows and never shows, what it writes down, and how the scripture views will plug in. Code: `apps/api/src/admin/`. What is stored about the people who use it is in `docs/PRIVACY.md`.

## What it is

[sqladmin](https://github.com/aminalaee/sqladmin) 0.32, mounted by the API at `/admin` and served on a host of its own, `ADMIN_URL` (`https://admin.tabsira.me`, `https://admin.tabsira.test` in development), which is reachable only through the VPN's DNS. The mount answers a request only when its `Host` is the host of `ADMIN_URL`: on any other host, `api.tabsira.me/admin` included, the answer is a plain 404 before any admin code runs. It is built only while `FEATURE_ADMIN` is true; with it off `/admin` is a plain 404 and no admin code runs.

The panel is **in English, left to right**. sqladmin's interface is a fixed English, left-to-right layout and making it right-to-left would mean forking its templates and stylesheets, which is not worth it for a tool two or three editors use. Arabic _content_ (terms, place names, learning units) is shown in its own direction (`unicode-bidi: plaintext`) so it reads correctly inside the English page. Nothing in the panel loads from another host: sqladmin's scripts, styles and fonts are served from `/admin/statics`.

## Signing in

An admin is an ordinary account with `users.is_admin`. Nobody becomes one from the web:

```bash
uv run python -m src.cli.make_admin you@example.com               # grant
uv run python -m src.cli.make_admin you@example.com --revoke      # take away
uv run python -m src.cli.make_admin you@example.com --reset-two-factor
```

Granting needs an account that can sign in (active, not deleted) and tells you when it has no password: the admin signs in with the account's e-mail address and password (the same bcrypt check as `/auth/login`), so a Google-only account first sets one through «forgot password». Revoking also deletes the account's admin sessions and second factor. Each command writes an audit row.

**Second factor.** An admin turns it on from the panel, under _Security > Two-factor sign-in_, in two steps so a phone that did not take the key never locks anyone out: _Start_ shows a key to type into an authenticator app ("enter a setup key", time-based, six digits; there is no QR code), then _Turn on_ asks for the first code, which also shows ten recovery codes, once. From then on the sign-in form needs a code from the app, or a recovery code (each works once). Switching it off asks for a current code or a recovery code. If both the phone and the recovery codes are lost, `make_admin --reset-two-factor` on the server removes the factor and ends the admin's sessions; the admin signs in with the password and enrols again.

`ADMIN_REQUIRE_TWO_FACTOR=true` makes the factor mandatory: an admin without it can sign in but reaches nothing except the enrolment page, the sign-out page and the static files until they turn it on. Leave it on in production once every admin has enrolled.

**What a refusal says.** Always «The e-mail address, the password or the code is wrong.» It never says which, so the form cannot be used to learn which addresses are admins or have a second factor. The password is checked even for an unknown address, against a decoy, so timing says nothing either. The real reason goes to the audit log (`bad_password`, `unknown_account`, `not_admin`, `account_disabled`, `code_missing`, `bad_code`, `rate_limited`).

**Rate limit.** The accounts limiter (`src/services/rate_limit.py`, kind `login`), per IP address and per e-mail address, `AUTH_ATTEMPT_WINDOW_SECONDS`, `AUTH_MAX_ATTEMPTS_PER_IP` and `AUTH_MAX_ATTEMPTS_PER_EMAIL`, checked before any password is hashed. A wrong password, a wrong code and a missing code each count; a success does not. Because it is the same kind as `/auth/login`, an attacker gets one budget for both doors, not two. Switching the second factor off asks for a code and counts the same way.

**Session.** A row of `admin_sessions` (the SHA-256 of a random 256-bit token, the user, a keyed hash of the address, the user agent) and one cookie, `__Secure-tabsira_admin`: httpOnly, Secure, SameSite=Strict, `Path=/admin`, no `Domain` (so it belongs to the admin host alone, unlike the user cookie), twelve hours, never extended. A new sign-in ends the session the browser held. The cookie holds nothing but the token.

**Every request is checked again.** `AdminAuth.authenticate` loads the session and requires the account to still be an active, undeleted admin. Revoking `is_admin`, deactivating or deleting the account ends its admin access on its next request, whatever the cookie says. A session that no longer qualifies is deleted and its cookie dropped.

**CSRF.** Every `POST`, `PUT`, `PATCH` and `DELETE` needs the session's token, in the `X-CSRF-Token` header or the `csrf_token` form field; without it the answer is 403 before any view runs, so a view added later is covered. The token is a keyed hash of the cookie's token, so nothing is stored and a page of another site cannot compute it. The templates put it in every form (sqladmin's `render_form_fields` macro is wrapped), in a meta tag the admin script reads, and the script sends it with deletes. Two more rules close the gaps sqladmin leaves: every custom action answers `POST` only (sqladmin registers them as `GET`, and the script posts them), and signing out is a `POST` from a confirmation page. The sign-in form has its own token, a keyed hash of a nonce set in a short-lived cookie. **Origins.** The admin is on the same _site_ as the web app (`admin.tabsira.me` and `tabsira.me`), so `SameSite=Strict` alone would still send its cookie from a page of the web app. Three rules hold regardless: the CORS layer is skipped for `/admin`, so no admin response ever carries `Access-Control-Allow-Origin` (nor does a preflight), whatever `Origin` a request names; `OriginCheckMiddleware` accepts a state-changing request under `/admin` only from `ADMIN_URL`'s own origin, not from `CORS_ORIGINS` and not from the API's origin, so a script in the web app can neither read the CSRF token nor use it; and the admin script (`tabsira-admin.js`) posts the token only to this origin, under `/admin/`.

**Headers.** Every admin response is `Cache-Control: no-store` (static files aside), `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff` and `Referrer-Policy: same-origin` (not `no-referrer`: with that policy a browser sends `Origin: null` on every form post, which the API's origin check refuses).

## Settings

| Key                               | Default                      | Meaning                                                                                                                                                                                          |
| --------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ADMIN_URL`                       | `https://admin.tabsira.test` | The admin's address. `/admin` answers this host only and takes state changes from this origin only. Production refuses a `.test` value.                                                          |
| `FEATURE_ADMIN`                   | `true`                       | Mounts `/admin`. Off means 404 and no admin code runs.                                                                                                                                           |
| `ADMIN_TOTP_ENCRYPTION_KEY`       | empty                        | Fernet key(s), comma separated, that encrypt the second-factor secrets: the first encrypts, all decrypt (rotate by putting the new key first). **Required in production while the admin is on.** |
| `ADMIN_REQUIRE_TWO_FACTOR`        | `false`                      | An admin without the factor reaches only its enrolment page.                                                                                                                                     |
| `ADMIN_AUDIT_RETENTION_DAYS`      | `400`                        | How long audit rows are kept (30 to 3650).                                                                                                                                                       |
| `ADMIN_AUDIT_COMPRESS_AFTER_DAYS` | `30`                         | Age after which audit chunks are compressed; under the retention.                                                                                                                                |

Production refuses to start with the admin on and no key. Elsewhere an empty key derives one from `HASH_SECRET`, so a development database needs no extra secret. Generate a key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If every key that encrypted a secret is lost, the factor cannot be verified and fails closed (a recovery code still works); reset it with the command above.

## What each view shows

Each view names its columns (the registry refuses one that does not), so a column added to a model later never appears by itself.

| View                                   | Shows                                                                                             | An admin can                                                                                                                               |
| -------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Dashboard                              | Counts of accounts, sessions, consents, candidates, entities, path versions, places, audit events | Follow a count to its list                                                                                                                 |
| Users                                  | E-mail, display name, active and admin flags, verified, created, updated                          | Rename an account and switch it on or off (not oneself). No create, no delete, no admin rights from here.                                  |
| Sessions                               | Who, when created, last seen, expires, user agent                                                 | **Revoke** the selected ones                                                                                                               |
| Consents                               | Who, kind, version, granted, when                                                                 | Read only                                                                                                                                  |
| Ontology candidates                    | Term, kind, how often proposed, sources, examples, status, reviewed when and by whom, note        | **Accept** or **reject** the selected ones (records the decision, the time and the admin); write the note, which also records the reviewer |
| Ontology entities                      | The imported ontology, without its raw cells and search forms                                     | Read only                                                                                                                                  |
| Learning path versions, domains, units | The imported path; units show evidence pointers (a surah and verse), never scripture text         | **Activate** one version (the previous one is switched off; the database allows one active)                                                |
| GeoNames                               | Places with their Arabic name, codes, population, coordinates, zone                               | Read only; search by name (Latin letters use the trigram index; Arabic letters read the unindexed Arabic name and take a few seconds)      |
| Audit log                              | Every row of the log below, newest first                                                          | Read only; filter by action, search by model or record                                                                                     |
| Two-factor sign-in                     | The admin's own enrolment state                                                                   | Turn the factor on and off for their own account                                                                                           |

No view exports and none imports: a CSV of accounts or consents is a copy of private data that leaves the audit trail. `register_view` refuses a view that switches either on.

## What never appears

- **A profile in any form.** Religious background, gender, age range, goals and knowledge level are private to their owner (`docs/PRIVACY.md`). There is **no profile view**, although decision 14 lists one: nothing an admin does here needs one, and a view that was added later would still pass through the rules below. The only account columns shown are the ones in the Users row above.
- Password hashes, session token hashes, address hashes (the audit log alone shows its own keyed address hash), the second-factor secrets and recovery codes, e-mail verification tokens, guest keys.
- The text a person wrote or typed: nothing in the admin stores or shows it, and the audit log keeps names, never values (below).

`tests/test_admin_privacy.py` walks every registered view and fails if any of these columns can reach a list, a record page, a form or an export; it also crawls every list, record and edit page of a database seeded with private answers and credentials and fails if one of them shows up.

## The audit log

`app.admin_audit_log` records every admin sign-in, failed sign-in and sign-out; every list page, record page, create, edit, delete and bulk action; every second-factor change; and every grant, revoke and reset done by `make_admin`. A row holds the time, the admin's account id, the action, the view (`user`, `ontology-candidate`, ...), the record id, a small JSON, a keyed hash of the client address and the user agent (cut to 256 characters).

**Names, never values.** The JSON holds only the names of the fields an edit changed, a reason code (`bad_password`, an action's name), and the ids a bulk action touched with their count. It is built by `admin_audit_service.details_of` from typed arguments and refuses a field name that is not a column name, so a value cannot get in; the search words of a list page are not recorded; the e-mail address typed at a failed sign-in is not recorded. A failed sign-in names the account when the address matched one.

**When rows are written.** Pages, sign-ins and bulk actions are recorded as the request arrives, so an attempt a view then refuses is still on the record. Create, update and delete are recorded by sqladmin's audit hook after the change is committed; sqladmin treats that hook as best effort and only logs if it fails.

**A hypertable.** Decision 13: the table is partitioned on its time column `at` with TimescaleDB (`create_hypertable`, one-week chunks; the primary key is `(at, id)`). A retention policy drops chunks older than `ADMIN_AUDIT_RETENTION_DAYS` and a compression policy compresses those older than `ADMIN_AUDIT_COMPRESS_AFTER_DAYS`, segmented by admin. The migration sets both from the settings; changing the settings later changes nothing by itself, so run

```bash
uv run python -m src.cli.audit_policy
```

to replace the policies with the new windows (safe to repeat).

**Append-only.** A trigger refuses every `UPDATE` and `DELETE`, for the application's own role too. Rows leave only when TimescaleDB drops a whole chunk for the retention policy, which does not run row triggers; compressed chunks stay append-only. The admin id and the record id are plain columns with no foreign key, so deleting an account neither fails nor rewrites the log; after the retention window they name nobody.

## Adding views: the extension point

Other parts of the product add their views without editing the admin. A module registers them:

```python
# apps/api/src/admin/scripture.py
from src.admin.base import ReadOnlyView
from src.admin.registry import register_view
from src.models.scripture import QuranVerse  # not in this repository yet

@register_view
class QuranVerseAdmin(ReadOnlyView, model=QuranVerse):
    name = "Quran verse"
    name_plural = "Quran verses"
    category = "Scripture"
    column_list = [QuranVerse.id, QuranVerse.surah, QuranVerse.ayah, QuranVerse.text_hash]
    column_details_list = [QuranVerse.id, QuranVerse.surah, QuranVerse.ayah, QuranVerse.text, QuranVerse.text_hash]
```

`install_admin` imports every module of `registry.EXTENSION_MODULES` that exists (today only `src.admin.scripture`, which does not exist yet and is skipped), so the views it registers are mounted after the built-in ones, and nothing in `src/main.py` or `src/admin/__init__.py` changes. A module that exists but fails to import is an error, not skipped.

`register_view` checks every view when it is registered, and an unfit view fails the import, so the process refuses to start. The rules are decisions 14 and 18 written as code (`registry.check_view_policy`):

- no view exports or imports;
- every view names `column_list`, `column_details_list` (when it has a record page) and `form_columns` (when it has a form);
- the tables `quran_verses` and `hadiths` hold scripture text: `can_create`, `can_edit` and `can_delete` must all be false, always;
- the table `hadith_rulings` is append-only: `can_create` may be true, `can_edit` and `can_delete` must be false.

A view starts from `AdminView` (names the changed fields for the audit log) or `ReadOnlyView` (no create, edit or delete). A custom action (`@action`) is a method of the view; it answers `POST` with the CSRF token and is audited automatically. A custom page (`BaseView`) that changes data writes its own audit row with `admin.trail.write(...)`, and a form of its own puts `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` in its template (sqladmin's create and edit forms already carry it). The running admin is `app.state.admin`.

## The scripture views, as the scripture store must build them

The scripture store (`quran_verses`, `hadiths`, `hadith_rulings`, `hadith_verification_queue`) is built elsewhere; these are the views it adds through `src/admin/scripture.py`. Decisions 14, 16, 17 and 18 govern.

**Text rows are read only.** `quran_verses` and `hadiths` get a `ReadOnlyView`. There is no create, edit or delete form for them, ever, and the registry refuses a view that tries. The text is shown byte for byte, in its own direction (`dir="rtl"`, `lang="ar"`), with its stored hash and the id of its source; it is never trimmed, normalised, completed or corrected, and no `column_formatter` may change it. The list shows the hash and the reference; the full text is on the record page.

**The dorar ruling queue.** Decision 18: dorar.net blocks automated access and is never called from the server; an editor opens dorar in a browser and records the ruling here. A hadith the pipeline wanted but that has no ruling yet is in `hadith_verification_queue` with a demand count, and until it has one the insight shows the verse alone.

- _The queue view_ lists the entries that have no ruling yet, **ordered by demand**, highest first, then oldest first. Columns: the hadith's collection and number, the hadith text (read only, for the editor to look up), how many times the pipeline wanted it, first and last time wanted. Search by collection and number. The queue is written only by the pipeline; the admin never edits or deletes an entry. Recording a ruling removes the entry from the default list because the list is "entries with no ruling" (a `NOT EXISTS` on `hadith_rulings`), so the queue row itself is untouched.
- _The ruling form_ is the create form of a `HadithRulingAdmin(AdminView, model=HadithRuling)` with `can_create = True`, `can_edit = False`, `can_delete = False`, opened from a queue entry (the hadith is fixed by the entry and is not a field). The editor types, copying from dorar:

| Field            | What                                                                                                                               |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `ruling_text`    | The ruling **exactly as dorar gives it**: stored byte for byte, no trimming, no normalising, no summary. A required text area.     |
| `scholar`        | The scholar dorar names (المحدّث).                                                                                                 |
| `source`         | The source book (المصدر).                                                                                                          |
| `page`           | The page or number in that book (الصفحة أو الرقم).                                                                                 |
| `dorar_url`      | The address of the dorar page the editor read. `https` only, host `dorar.net` or a subdomain; checked when the form is validated.  |
| `classification` | One of صحيح, حسن, ضعيف, موضوع, مختلف فيه, stored as stable codes (`sahih`, `hasan`, `daif`, `mawdu`, `disputed`), shown in Arabic. |

The row also carries the **admin and the time**, set by the server in `on_model_change` (`recorded_by = current_admin(request)`, `recorded_at` from the database) and never a form field. Only `sahih` and `hasan` make a hadith eligible as evidence; the pipeline derives eligibility from the rulings, and the admin never sets it directly.

- _Append-only._ A ruling is inserted and then stands: the table gets the same refusal of `UPDATE` and `DELETE` as `consents` and the audit log (a trigger, in the migration that creates it). A mistake is corrected by recording a new ruling, and the latest row of a hadith is the one in force. How several rulings by different scholars combine into one eligibility is not decided in decision 18; until the owners decide, take the latest.
- _Audit._ Creating a ruling is a `create` audit row (`model` `hadith-ruling`, the record id, the **names** of the fields, never the ruling text), written by the create hook with no extra code. The queue and ruling views are audited like every other view.
- _The reader's side_ is not this view: every displayed hadith carries a «تحقق في الدرر» link the reader opens.

## Operating it

nginx proxies `admin.tabsira.me` (redirecting `/` to `/admin/`, and passing the `Host` header on, which the API's host check needs) with a content security policy that allows what the panel loads (its own scripts and styles, inline scripts, forms to itself). The API must run with proxy headers so that the rate limit and the audit log see the client's address, not nginx's (`docs/AUTH.md`, "Behind nginx"). Everything is tested through HTTP (`apps/api/tests/test_admin_*.py`, with a fixed clock for the second factor and the hypertable built in the test database), at 100 % line and branch coverage.

## Choices and what is not built

- English, left-to-right panel; Arabic data shown in its own direction (above).
- No profile view and no export (above).
- No QR code for the second factor: the key is typed in, which every authenticator app supports. A QR code would need an image library for a handful of editors.
- sqladmin keeps one set of view classes per process, so one admin per process; the API builds exactly one.
- The scripture, moderation, insight, post, comment, report, block, map and AI-cost views of decision 14 are added with the features they show, through the extension point above.
