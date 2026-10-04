# Error tracking with GlitchTip

Decision 24 of `docs/spec/DECISIONS.md`. Optional: it is on only when `GLITCHTIP_DSN` is set. This page says what is collected, when, how it is cleaned, and how the browser's errors get to GlitchTip without a key in the bundle. It is ported from the reference project's `docs/ERROR_TRACKING.md` and trimmed to what TABSIRA needs; what is stored about people is in `docs/PRIVACY.md`.

GlitchTip speaks the Sentry protocol, so the official `sentry-sdk` (2.71 at the time of writing, from PyPI) does the sending on the API. The web app has no SDK.

| Piece                                    | File                                                                                                                    |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| SDK setup, scrubbing, release, forwarder | `apps/api/src/error_tracking.py`                                                                                        |
| Start-up and shutdown flush              | `apps/api/src/main.py` (`create_app`, `lifespan`)                                                                       |
| Request id tag                           | `apps/api/src/middleware/request_id.py`                                                                                 |
| Browser reports endpoint                 | `apps/api/src/routers/client_errors.py`                                                                                 |
| Browser reports schema                   | `apps/api/src/schemas/client_errors.py`                                                                                 |
| Body size cap                            | `apps/api/src/middleware/body_limit.py`                                                                                 |
| In-memory rate limiter                   | `apps/api/src/services/window_limiter.py`                                                                               |
| Browser family of a user agent           | `apps/api/src/user_agent.py`                                                                                            |
| Configuration                            | `.env.example`, section "Error tracking"                                                                                |
| Tests                                    | `test_error_tracking.py`, `test_client_errors.py`, `test_body_limit.py`, `test_window_limiter.py`, `test_user_agent.py` |

## 1. Rules

1. **Nothing is sent without a DSN.** `GLITCHTIP_DSN` empty starts no SDK and builds no client: there is no code path that could send anything. `POST /client-errors` still answers 204 and drops the report.
2. **No personal data.** `send_default_pii` is off. No user is attached to an event: no id, no e-mail, no name, no address, no cookies. The browser is reduced to its family (`chrome`, `firefox`, `safari`, `edge`, `opera`, `samsung_internet`, `other`).
3. **No request bodies, ever** (`max_request_body_size="never"`), and no local variables in stack frames (`include_local_variables=False`), which is where a photo, a profile field or a verse would otherwise travel.
4. **Names decide what is private** (section 5): tokens, secrets, the fields of a profile, a photo or a location. The masked value is `[Filtered]`.
5. **Arabic text is replaced everywhere.** The product's own diagnostics are English, so Arabic in an error is a person's words or scripture. Each run becomes `[Arabic text]`. Events raised under `/scripture` lose all their free text.
6. **Reporting never slows or breaks the product.** The transport runs on the SDK's worker thread with a 2 s budget, the flush at shutdown waits 2 s at most, and `init_error_tracking` catches everything: a bad DSN leaves the process running without reporting.
7. **A fixed trace sample rate**, 0 by default: errors only. A caller cannot force its request to be timed with a `sentry-trace` header, and no `sentry-trace` or `baggage` header is added to requests to the AI providers or any other service.
8. **Release names carry the service**: `tabsira-api@…`, `tabsira-web@…`, because GlitchTip shares releases across an organisation.

## 2. Projects and keys

| Project       | Platform   | Setting             | Who sends                                                |
| ------------- | ---------- | ------------------- | -------------------------------------------------------- |
| `tabsira-api` | Python     | `GLITCHTIP_DSN`     | The API process                                          |
| `tabsira-web` | JavaScript | `GLITCHTIP_WEB_DSN` | The API, on the browser's behalf (`POST /client-errors`) |

Both DSNs live only in the API host's `.env`; the web bundle carries none. `GLITCHTIP_WEB_DSN` empty sends the browser's reports to the API project, tagged `area=web`, so one DSN is enough to start. Production and staging share the projects and are told apart by `environment`. Production refuses a DSN whose host ends in `.test`.

## 3. The pipeline

```text
 boot                      one request
 ├─ create_app()           ├─ RequestIdMiddleware tags request_id
 │   └─ init_error_tracking│   (the id the response and the access log carry)
 │      (before the app    ├─ Starlette and FastAPI integrations: the route
 │       is assembled)     │   pattern names the transaction
 └─ lifespan shutdown      ├─ SQLAlchemy: the statement, placeholders only
     └─ flush (2 s)        └─ log records: INFO..WARNING breadcrumb, ERROR issue
                                       │
                       before_send / before_send_transaction (scrub_event)
                                       │
                       POST https://<host>/api/<project>/envelope/  (2 s budget)
```

- `init_error_tracking(settings, version)` runs at the top of `create_app`, **before** `FastAPI(...)`: the integrations hook the framework as the application is assembled, so a later start would report nothing.
- Errors are unhandled exceptions and `log.error(..., exc_info=...)` records. The API's catch-all handler logs and answers 500, so an unhandled exception is one issue, not two (the SDK de-duplicates). 4xx responses are not issues.
- `before_send` renames the event `VERB pattern` (`GET /scripture/quran/{surah}`, never the path with its ids) and then scrubs it.
- Integrations are explicit: Starlette, FastAPI, SQLAlchemy and logging. `auto_enabling_integrations` is off; the `argv` and installed-package integrations are disabled (`sys.argv` can carry an address).

## 4. SDK options

| Option                                                                          | Value                                                      |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `dsn`                                                                           | `GLITCHTIP_DSN`                                            |
| `environment`                                                                   | `ENVIRONMENT` (`production`, `development`, `test`)        |
| `release`                                                                       | `tabsira-api@<version>` (section 6)                        |
| `server_name`                                                                   | the host name                                              |
| `sample_rate`                                                                   | `1.0`: every error                                         |
| `traces_sampler`                                                                | fixed `GLITCHTIP_TRACES_SAMPLE_RATE`; absent while it is 0 |
| `send_default_pii`                                                              | `False`                                                    |
| `max_request_body_size`                                                         | `never`                                                    |
| `include_local_variables`                                                       | `False`                                                    |
| `trace_propagation_targets`                                                     | `[]`: no trace header leaves for another service           |
| `shutdown_timeout`                                                              | `2`                                                        |
| `auto_session_tracking`, `send_client_reports`, `enable_metrics`, `enable_logs` | all off                                                    |
| `transport`                                                                     | `ShortTimeoutTransport` (2 s instead of 30)                |
| `before_send`, `before_send_transaction`                                        | `before_send`: route name, then scrub                      |

## 5. Scrubbing

`scrub_event` runs on every event and transaction, API and browser alike.

- **Request.** The body, cookies, query string and environment are removed. The URL loses credentials, query and fragment. Only `Content-Type`, `Content-Length`, `Accept`, `Host` and `Origin` headers stay, and `User-Agent` becomes its family. `Authorization`, `Cookie`, `X-Forwarded-For` and every other header are gone.
- **User.** Dropped, if the SDK attached one.
- **Text** (`scrub_text`): a query string (`?name=value&...`) is removed whole wherever it is written, whatever its names; the value of every `name=value` pair whose name is private becomes `[Filtered]`; every run of Arabic script becomes `[Arabic text]`. Applied to the message, the log entry and its parameters, each exception value, the transaction name, every breadcrumb message and every span description.
- **Mappings** (`scrub_mapping`): a private key has its value replaced; other values are scrubbed. Applied to `extra`, `tags`, `contexts`, breadcrumb data and span data. Bytes are never sent.
- **A private name** is one that contains `pass`, `secret`, `token`, `checksum`, `api_key`, `authorization`, `cookie`, `session`, `csrf` or `credential`, ends in `pw`, or contains as a whole word `email`, `display_name`, `age_range`, `religious…`, `gender`, `goals`, `knowledge_level`, `profile`, `photo`, `image`, `picture`, `avatar`, `exif`, `gps`, `latitude`, `longitude`, `lat`, `lng`, `lon`, `location`, `coordinates`, `address`, `phone`, `verse`, `hadith`, `scripture`, `quran`, `text`, `body`, `caption`, `prompt`, `search` or `note`. A whole word means nothing alphanumeric touches it, so `context` is not `text`.
- **Scripture routes.** An event whose request path is `/scripture` or below has its message, log entry, exception values, `extra`, breadcrumbs and span descriptions replaced by `[Scripture route: text filtered]`. The exception type, the frames and the route stay: that is all a fix needs. The same rule applies to a browser report from a page under `/scripture`.

`test_error_tracking.py` covers each function, then runs the real SDK against a recording transport and asserts on the event that would have been sent.

## 6. Naming

`<service>@<version>`, at most 200 characters. The version is, in order: `GLITCHTIP_RELEASE` when set (a copy deployed without its history); the checkout's `git describe --tags --long --always` as semver with build metadata; the API's package version.

| `git describe --long` | release                             |
| --------------------- | ----------------------------------- |
| `v1.0.0-0-gabc1234`   | `tabsira-api@1.0.0`                 |
| `v1.0.0-32-gdbbab302` | `tabsira-api@1.0.0+32.gdbbab302`    |
| no tag, commit only   | `tabsira-api@<first 12 characters>` |
| no git at all         | `tabsira-api@0.1.0` (package)       |

A plain `1.0.0-32-gdbbab302` would read as a pre-release older than 1.0.0; the `+` form sorts after it.

Tags on every API event: `area=api`, `request_id` (the `X-Request-ID` the response carries, so a report can be matched to a log line). Browser events carry `area=web`, `browser=<family>` and the same `request_id`.

## 7. The browser

The web bundle carries **no DSN**: a key in client code is a key anyone can flood, and the visitor's browser makes no third-party request (decision 24).

1. The web app collects `window.onerror`, `unhandledrejection` and its two Next error boundaries, queues the reports and posts them in small batches to `POST /client-errors` on the API, with `fetch` or `sendBeacon`. A report sets no cookie, keeps nothing on the device and carries no personal data, so it is outside the consent categories of decision 32; the privacy page names it all the same.
2. `POST /client-errors` needs **no sign-in**: an error can happen on the sign-in page itself. Its bounds:
   - **Schema** (`ClientReportBatch`): 1 to 10 reports; a message of 1 to 2 000 characters; a stack of at most 16 000; at most 20 breadcrumbs of 500 characters; at most 20 context keys, scalar values only; a release that is `[\w.+-]` and at most 100 characters. A failure is the usual `422`.
   - **Size**: a body over 256 KiB is refused with `413 PAYLOAD_TOO_LARGE` from its `Content-Length`; without a length (chunked) it is cut at the cap and then fails the schema.
   - **Rate**: 60 reports per 5 minutes per address (a keyed hash of it, never the address), and 600 per 5 minutes over all addresses; then `429 RATE_LIMITED` with `Retry-After`. The counters are in the memory of each worker, so with N workers the budget is N times that: a spam bound, and it costs no database write when the database is the thing that is failing.
   - **Origin**: like every state-changing request it must come from `CORS_ORIGINS`.
3. Each report becomes an event on the web project: `platform: javascript`, `area: web`, the browser family, the API's `request_id`, the page URL without its query, the stack parsed into frames (V8 and Gecko shapes) or kept as text, and the breadcrumbs. The client has its own scope, so nothing from the API request leaks into it.

The answer is `204 No Content` in every accepted case, and also when no DSN is set, so a stale tab never errors on its own error report.

## 8. What the owners must know

- GlitchTip is a third party that receives error reports from the API server: stack traces of our code, route patterns, release and environment, and the cleaned texts above. It receives nothing from the visitor's browser directly.
- A report from a page cannot be trusted: it is bounded and cleaned, but its content is whatever the sender wrote.
- Arabic is removed even from our own Arabic messages. Diagnostics stay in English (`src/messages.py` holds what people read).

## 9. Porting checklist (kept from the pattern)

1. Official Sentry SDK; no custom client.
2. A DSN setting; empty means off; the test suite scrubs every setting from the environment.
3. Initialise once, before the app is built.
4. Release `<service>@<git describe as semver+build>`.
5. A request id tag; no user.
6. Hook the logging library: breadcrumbs from INFO, issues from ERROR.
7. Scrub every `before_send`; test each function and a whole event.
8. Flush at exit; short transport timeouts.
9. Keep it out of customer documentation.
