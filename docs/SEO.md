# SEO and indexing standard

TABSIRA follows the playbook in `the SEO playbook` (README §12 SEO, §26 launch checklist: "Nothing here is optional"), adapted to one language (Arabic) and to user-generated public pages. Reference implementations: `~/workspace/the reference site/scripts/{check-seo,check-site,indexnow}.mjs` and `the reference project/scripts/indexnow.mjs`. Decisions 28–30 in `docs/spec/DECISIONS.md` govern analytics, the sitemap and the language.

## 1. Technical

- **One URL form:** `https://tabsira.me/<path>` without a trailing slash, used identically in canonicals, `og:url`, sitemap entries and alternates. The built HTML must carry the production origin; a build that leaks `localhost` or `.test` fails.
- **Canonical** on every indexable page, self-referencing. **hreflang:** `ar` and `x-default`, both pointing to the same URL.
- `<html lang="ar" dir="rtl">` on every page.
- **robots.txt** from the app: names the sitemap index only (never the children), no `Host:` line, and lists every AI agent explicitly — GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-SearchBot, Claude-User, Google-Extended, GoogleOther, PerplexityBot, Perplexity-User, Bingbot, Applebot-Extended, meta-externalagent, Amazonbot, CCBot, DuckAssistBot, MistralAI-User. Policy: all allowed (owners may restrict training crawlers later). Private areas (`/me`, `/admin`, `/dev`, API) are disallowed and `noindex`.
- **Sitemap** (decision 29): index at `/sitemap.xml` plus one child per content kind (`static`, `insights`, `posts`, `places`, `profiles`), built with the `sitemap` package from the API; never Next's own sitemap convention (it can claim `/sitemap.xml` and emit nothing). `lastmod` is the record's own update date, never the build clock; omitted when unknown. The index `lastmod` is the newest child `lastmod`.
- **Every route outside the sitemap is `noindex`** (an exported `UNLISTED_ROUTES` list, even when empty).
- **Status codes:** real 404 with no redirect, an inline-styled page without font dependency, the requested path shown as LTR text; permanent redirects are 308 (`permanentRedirect()`), only on evidence; legal pages indexed with `max-snippet:0`.
- **Pagination:** each page has its own canonical; page 1 and pages past the last 308 to the base URL.
- **Rendering:** text is server-rendered; lists render whole on the server; navigation is `<ul>/<li>`; adjacent inline elements keep a real space so text extraction never welds words.
- **Performance:** self-hosted fonts split by `unicode-range` with one preload per page (the Arabic UI face), images at 3× layout width in WebP with real aspect-ratio slots, below-the-fold images never `priority`, no scroll listeners or parallax, `/_next/static` immutable for a year and HTML `expires -1`. Target LCP ≤ 2.5 s on a throttled mobile profile.

## 2. Metadata

- `<title>` ≤ 65 characters and description ≤ 165, measured after decoding entities; the title carries the phrase people would search and uses a pipe: `تبصرة | <page>`.
- A separate share line per page (the reason to tap), distinct from the hero headline.
- **Share card per page**, named explicitly by route: JPEG under 300 KB (11–86 KB typical), 1200×630, drawn in the page's colours. Arabic card rules: one font per card (IBM Plex Sans Arabic, full font for user-generated text), U+00A0 for spaces, headline broken at a clause boundary, `direction` set on every text node, no U+200F. Insight cards never render Quran or hadith text inside the image (decision on scripture); the user's photo appears only with consent and never for a sensitive scene.
- `og:type` (`website`, `article` for insights and posts), `og:locale` `ar_AR`, `twitter:card` `summary_large_image`.
- **Icons** built by one script from the master mark SVG and committed: `favicon.ico` (16/32/48), `apple-icon` 180 opaque, `icon-192`, `icon-512`, `maskable-512` with the mark in the safe zone, `mstile-150` + `browserconfig.xml`; the manifest declares exact sizes and is served as `application/manifest+json`; `theme-color` has light and dark values.

## 3. Structured data (`schema-dts`, present in the built HTML)

- `Organization` with a stable `@id`, a square logo ≥ 112 px and `sameAs` from the real accounts; `Person` for the founders (Firas Ben Sassi, Ghazi Triki) with `worksFor`; `WebSite`; `BreadcrumbList` on every non-home page derived from the shared routes.
- `Article` for public insights and posts: `headline`, `datePublished`, `author` (the public display name only). `SoftwareApplication` for the app page without `offers`. `FAQPage` only for real questions.
- Never a fact in JSON-LD that the page does not print. Nothing beyond these types.

## 4. Content

- Exactly one `h1`; `alt` on every image (`alt=""` for decorative ones); headings carry their meaning alone; the definition of the page in its first 100 words; sentences under 28 words.
- Arabic conventions: Western digits, quotation marks « », Arabic punctuation ، ؛ ؟, Latin product names wrapped in `<bdi>`, logical CSS properties, no letter-spacing or uppercase on Arabic text, formal address.
- No em or en dashes in visible copy, no unbackable claims, no dated counts.
- `llms.txt` and `llms-full.txt` generated from the routes and the messages module (useful to agents, not a ranking lever).
- **Public user content:** public profiles, posts and insights expose only what their owner published (display name, chosen photo, insight, verified texts); never profile fields, location beyond the published approximation, or private history. A withdrawn item answers 410 and leaves the sitemap at the next build.

## 5. Indexing

- **IndexNow** (Bing, Yandex, Naver, Seznam, Yep, Amazon; Google does not take part): `scripts/indexnow.mjs` ported from the reference project, no npm package. A key file `apps/web/public/<key>.txt` whose name equals its content, generated by an idempotent `--init` and committed. State in `INDEXNOW_STATE` outside the release directory; only new or changed URLs (by `lastmod`) are sent. It runs **last in a production deploy**, after the nginx reload and the health check; a failure warns and exits 0. Production only: it refuses (a warning, exit 0) unless `SITE_URL` is `https://tabsira.me`, or `--force` is given. It reads the sitemap index from `SITEMAP_URL` (default the web app on loopback), sends only URLs of `SITE_URL`, in batches of 10 000, takes 200 and 202 as received, and writes down each accepted batch at once, so a refused batch is retried alone next time. `--dry-run` reports what it would send. Tests: `scripts/indexnow.test.mjs` with `node --test` (run by `make test`), no network.
- **Google Search Console** and **Bing Webmaster Tools** after launch: submit the sitemap index, review coverage per child sitemap monthly. Verification by DNS record or meta tag from the owners.

## 6. Analytics (decision 28)

- GA4 only when `GA_MEASUREMENT_ID` is set; unset means no analytics code and no banner.
- Consent Mode v2 defaults (all denied) run first; **the Google script is injected only after the visitor accepts**, so no request reaches Google before consent.
- Banner: reject as prominent as accept, nothing pre-ticked, no cookie wall, a «إعدادات ملفات تعريف الارتباط» link reopens it, the stored answer is versioned.
- Calls to action carry `data-analytics` handled by one delegated listener. The cookie policy and the privacy notice name GA and what it never receives.

## 7. Checks

`check:seo`, `check:site` and `check:a11y` (axe, WCAG 2.2 AA) are ported from the reference site and run against a running server (`BASE_URL`) in CI: title and description lengths, canonical form, hreflang, one `h1`, `lang`/`dir`, `alt`, text-extraction welding, share tags, icons and manifest sizes, consent defaults before any Google script, `noindex` on unlisted routes, and internal links.

In practice: `check:seo` and `check:site` run in the Jenkinsfile stage "Web SEO Checks" against the production build started on loopback (`SITE_URL` is the origin the build was made for; the page lists live in `apps/web/scripts/lib/site-routes.mjs`, a copy a unit test keeps equal to `src/lib/seo.ts` and `src/lib/crawlers.ts`). `check:a11y` needs a local Chromium and the API's sample answers, so it is run by hand (`pnpm --filter @tabsira/web check:a11y`) until a CI agent has Chromium. Pages still to come (insight, place, public profile) use `pageMetadata`, `breadcrumbJsonLd` and `articleJsonLd` of `src/lib/seo.ts`; a route outside the sitemap is added to `UNLISTED_ROUTES`. Heatmaps (decision 32): `CLARITY_PROJECT_ID`, loaded after the behaviour category, with `data-clarity-mask` on `<body>`.

## 8. Inputs from the owners

Master mark SVG (square, ≥ 112 px) and wordmark; `sameAs` profile URLs; the GA measurement id; Search Console and Bing Webmaster access; the AI-crawler policy if it should differ from "all allowed"; the legal revision date and contact address.

## 9. The sitemap API

What the web app reads to write the index and the children of section 1 (decision 29). Code: `apps/api/src/routers/sitemap.py` and `services/sitemap_service.py`. No sign-in; both answers carry `Cache-Control: public, max-age=300`.

- `GET /sitemap` returns `{page_size, sections}`: for each advertised section, its pages as `{page, lastmod}`, numbered from 0, where `lastmod` is the newest change date on that page. The index `lastmod` of the web app is the newest of all of them. A section with nothing to list has no pages; a section whose feature flag is off is missing.
- `GET /sitemap/{section}?page=N` returns that page as a list of `{path, lastmod, images}`. `path` is a path of the web app (the web app adds `https://tabsira.me`); `lastmod` is the record's own change date in UTC, or null; `images` are absolute `https://` addresses of pictures the page shows. A page past the last is empty. An unknown section or a negative page is a 422; a section that is switched off is a 404.
- Sections, in order, and the flag that switches each one on: `static` (always: `/`, `/about`, `/terms`, `/privacy`, `/cookies`, `/support`, each with a constant date set in code that changes only when the page's text does), `insights` (`FEATURE_WORLD`), `posts` (`FEATURE_SOCIAL`), `places` (`FEATURE_ATLAS`), `profiles` (`FEATURE_SOCIAL`). `insights` and `places` list nothing until their feature registers a provider; `posts` and `profiles` are registered by the social network (`services/social_sitemap.py`, `docs/SOCIAL_NETWORK.md`) and list only public, published posts of active accounts and the profiles that have one.
- `SITEMAP_PAGE_SIZE` (default 10 000, at most the protocol's 50 000) is the most entries on a page. Pages are cut in a stable order, oldest first, so a new record changes only the last page of its section.
- A feature plugs in by calling `sitemap_service.register(provider)` with an object that has a `section`, `pages(db, page_size)` and `entries(db, page, page_size)` (the `SitemapProvider` protocol). A provider lists only public, published, non-withdrawn content, and only photos their owner published. The service drops, and logs, an entry whose path is not in the one URL form of section 1, one whose `lastmod` has no time zone, and an image that is not `https`.
