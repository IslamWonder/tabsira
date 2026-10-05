# Design decision

**Status: decided on 4 October 2026** by Ghazi Triki: direction **C · ليل الأنوار** for structure and the dark theme, with **A's colours for the light theme**. The owners left the remaining UI and UX choices to the implementer; nothing is taken from the challenge's own website.

The three directions are drawn on one canvas, three phone screens each (the rain scene, the insight at full scroll height, the fog world): <https://claude.ai/artifact/E7FYkF4dw4aqzbh4HkM4XW>. The verse (Ar-Rum 30:50) and the hadith (al-Bukhari 1032) in the mockups were filled from the corpora and checked equal to their source, byte for byte.

## What every direction shares

- Arabic, right-to-left, phone first; WCAG 2.2 AA contrast; touch targets of at least 48 px; no motion on hover; the two pulsing calls on the photo stop under reduced motion.
- The rain scene first, marked «مثال موثّق مُعدّ», with exactly two insights in the photo (Hick's law, Choice overload) and one quiet secondary action «أو صوّر مشهدك أنت» (Occam's razor).
- The insight follows `tajriba.md` §6: title and glimpse, «ما ظهر» kept apart from interpretation, the Quran then the Sunnah, each labelled with its reference and «افتح المصدر», the platform's explanation labelled as such, «لماذا ظهر هذا؟», one small step with «سأفعله لاحقًا» (decision 45), the chat with its three-question limit, the AI disclosure line, and a single primary «تمّ» in the thumb zone (Fitts's law, Von Restorff effect).
- The hadith is shown whole, exactly as stored. The chain of narrators is set smaller and quieter and the Prophet's words stand out; this is presentation only, no character is added or removed. **To confirm by the owners.**
- Five tabs with the camera in the centre: عالمي، تواصل، التقط، الأطلس، ملفي (Jakob's law, Serial position effect).
- The world is a fog map: a place appears where an insight was saved, and a dotted thread joins two places only when a relation is recorded (Zeigarnik effect, Goal-gradient effect without scores).

## The directions

|          | A · نهار مزهر                                                   | B · مخطوطة مذهّبة                                         | C · ليل الأنوار                                      |
| -------- | --------------------------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------- |
| Feeling  | Joyful daylight, airy, familiar                                 | Heritage, calm, scholarly                                 | Immersive, contemplative, cinematic                  |
| Ground   | White and mint `#F6FAF7`                                        | Parchment `#F3EBD8` with a hairline lattice               | Night `#0B1210`                                      |
| Accents  | Emerald `#0F4C3A`, gold `#C6A15B` (text gold `#7A5A1C`)         | Emerald, gold leaf `#A8812F`, vermilion rubrics `#9E3324` | Glow emerald `#3FD69A`, light gold `#E6C77F`         |
| Type     | El Messiri titles, IBM Plex Sans Arabic text, Noto Naskh hadith | Amiri titles and hadith, Markazi Text interface           | Reem Kufi titles, Readex Pro text, Noto Naskh hadith |
| Photo    | Rounded card, white pills with pins                             | Mihrab-arch gilded frame, cartouches, eight-point stars   | Full bleed, glowing points, dark glass labels        |
| Quran    | Mint card, Uthmani script                                       | Centred like a mushaf page under a framed heading         | Ivory script on a soft gold glow                     |
| Strength | Clearest and most familiar; the safest for first-time users     | The most distinctive and the closest to the subject       | The strongest "wow" for the video; photos shine      |
| Risk     | Can look like many apps                                         | Dense; harder to keep light on small phones               | Dark UI is harder for long reading and in daylight   |

All three use the KFGQPC Uthmanic Hafs font for the Quran.

## Choice

### Structure (from C, both themes)

- The photo is the stage: full bleed on the scene screen, 330 px tall and fading into the page on the insight screen.
- Insights on the photo are glowing points with glass labels; at most three, each a real `<button>` with an equivalent list for screen readers and keyboards.
- Floating pill navigation with five tabs and the glowing capture button in the centre: عالمي، تواصل، التقط، الأطلس، ملفي.
- Headings in **Reem Kufi**, interface text in **Readex Pro**, hadith in **Noto Naskh Arabic**, Quran in **KFGQPC Uthmanic Hafs**, ornate brackets ﴿ ﴾ in **Amiri**. All fonts self-hosted.
- The world is a night map in dark mode and a mist map in light mode; places glow where an insight was saved; a thread joins two places only for a recorded relation, with «كيف ترتبطان؟» on it.

### Themes

The theme follows the device (`prefers-color-scheme`) and can be set to light, dark or automatic in «ملفي». Both themes share every layout and component; only tokens change.

| Token                                   | Dark (C)                                   | Light (A colours)                        |
| --------------------------------------- | ------------------------------------------ | ---------------------------------------- |
| `bg`                                    | `#0B1210`                                  | `#F6FAF7`                                |
| `surface`                               | `rgba(255,255,255,.05)`                    | `#FFFFFF`                                |
| `surface-glass`                         | `rgba(20,32,28,.72)` + blur 16 px          | `rgba(255,255,255,.86)` + blur 16 px     |
| `border`                                | `rgba(255,255,255,.14)`                    | `#DCE7E1`                                |
| `text`                                  | `#EEF3EF`                                  | `#16302A`                                |
| `text-soft`                             | `#C3D4CC`                                  | `#4A635C`                                |
| `text-muted`                            | `#93A79E`                                  | `#5F6F69`                                |
| `primary`                               | `#3FD69A`                                  | `#0F4C3A`                                |
| `primary-fill`                          | gradient `#4FDCA3 → #1F9E6E`, glow         | `#0F4C3A`, soft shadow                   |
| `on-primary`                            | `#04130D`                                  | `#FFFFFF`                                |
| `quran-accent` (label, frame, brackets) | `#E6C77F`                                  | `#9A7430` (brackets), label on `#0F4C3A` |
| `quran-surface`                         | gold wash `rgba(230,199,127,.12 → .03)`    | mint `#EEF7F2`, border `#CFE6DA`         |
| `sunnah-accent`                         | `#8FEAC2`                                  | `#7A5A1C`                                |
| `sunnah-surface`                        | emerald wash `rgba(63,214,154,.10 → .02)`  | warm `#FBF8F0`, border `#EFE4CB`         |
| `link`                                  | `#7FE3B8`                                  | `#0F4C3A`                                |
| `photo-scrim`                           | night gradients                            | white gradients                          |
| `glow` (points)                         | gold `#E6C77F` and emerald `#3FD69A` halos | emerald dot, gold `#FFD978` halo         |

Every text pair is checked at 4.5:1 (3:1 for 24 px and larger) in both themes before it ships; gold is never used for small text in light mode.

### Hadith display

The hadith is shown whole, exactly as stored. The chain of narrators and the closing notes are set smaller and in `text-muted`; the Prophet's words are set larger and stronger. This is presentation only: the spans are cut from the stored text by position and their concatenation is tested equal to it.

### Motion and sound

Motion on display and on events only, never on hover: the points breathe on first view, the insight sheet rises, the fog lifts from a place after «تمّ». Everything stops under reduced motion. Sound effects are a separate later task (owner, 4 October 2026); none are built now.

### Responsive web application (added 4 October 2026)

TABSIRA is a web application first, installable as a PWA, and works from a 320 px phone to a 1920 px desktop. The phone mockups above are one breakpoint, not the product. Layout changes with the space; tokens, components and copy stay the same.

| Breakpoint | Width       | Navigation                                                                                                            | Layout principle                            |
| ---------- | ----------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Phone      | < 768 px    | Floating pill bar at the bottom, capture in the centre                                                                | One column; sheets rise from the bottom     |
| Tablet     | 768–1199 px | Top bar: wordmark at the start (right), the four sections as tabs, «صوّر مشهدًا» as the one primary button at the end | Two columns where the content has two parts |
| Desktop    | ≥ 1200 px   | Same top bar, content up to 1440 px wide, centred                                                                     | Stage and reading side by side              |

Per screen:

- **Scene (`/`)** — desktop: the photo is the stage on the larger side (about 60 %, full height under the top bar), with its glowing points; the start side holds the wordmark line, «المس البصيرة التي لفتتك», the same insights as a short list (the screen-reader list made visible — Common Region, Serial Position), and the new-scene actions: drag-and-drop a photo, choose a file, paste a link, use the camera when the device has one (Postel's law: accept every input form). Phone: full-bleed photo as in the mockup.
- **Analysis** — the photo stays on screen while the honest stages run beside it (StageOrbit on desktop, a compact line on phones); nothing jumps when the result arrives (Doherty threshold: feedback under 400 ms, then calm).
- **Insight** — desktop: the photo is sticky on one side with the focused point highlighted, the reading column (680 px measure) on the other: title, «ما ظهر», Quran, Sunnah, «شرح تبصرة», «لماذا ظهر هذا؟», the step, the chat; the primary «تمّ» sits at the end of the reading column and in a sticky footer of that column. On screens ≥ 1440 px the Quran and Sunnah cards may sit side by side only when both texts are short (under ~280 characters); long texts always stack (tajriba §6: never force two long texts into narrow columns).
- **World** — desktop: the fog map fills the main area; the places list is a visible side panel (the accessible alternative becomes a feature), selecting in either highlights the other.
- **Atlas** — desktop: MapLibre map with a results side panel (insight cards in the visible area, filters on top); phone: full map with a bottom sheet. The camera discovery is offered only on devices with a camera and orientation sensors; on desktop the button explains it is a phone feature.
- **Community** — desktop: a centred feed column (≤ 640 px) with a side column for the «لك» / «أتابع» tabs and filters; phone: tabs on top of the feed.
- **Me** — a settings layout with a section list on the start side on desktop, a single list on phones.

Kept from the earlier prototype's look: the eight-point star mark beside the gilded wordmark, the soft aurora with a faint geometric pattern behind light-theme pages (it becomes a deep night aurora in dark), slow light motes (never pointer-driven), StageOrbit and QuestLog for progress, and the burst on «تمّ». Sound effects come later as a separate task. Not kept: the bottom navigation on wide screens and the narrow centred column on desktop.

Desktop interactions: every action reachable by keyboard with visible focus; hover may change colour or reveal a tooltip but never moves or resizes anything; drag-and-drop has a button equivalent.

### Capture first, one type scale, one scroller (added 5 October 2026)

The owners asked for the capture to be the core of the first screen and for the text to be smaller and the same everywhere (decision 62).

- **Scene on a phone.** The rain photo takes the top 62 % of the screen and fades into the page; «المس البصيرة التي لفتتك» sits above the fade, and the capture card rises from it: «صوّر مشهدك أنت», a one-line promise, «التقط صورة» (the one glowing call, Von Restorff) and «اختر صورة» side by side (Hick: two ways in), and the privacy line. The page scrolls only to the footer. The title stays for screen readers.
- **Scene from tablet up.** Title, promise, the insights as a list, then the same capture card, which also takes a dropped photo (said only to a fine pointer).
- **Camera sheet.** Viewfinder 3∶4 on a phone (4∶3 from tablet up) with corner marks and one line «وجّه الكاميرا إلى ما لفتك، ثم التقط.»; «أغلق الكاميرا» on the viewfinder; under it the 76 px shutter in the middle, the gallery on the start side and the other camera on the end side. No live camera: the summoning circle, the reason, then «التقط بالكاميرا» (the phone's camera app) and «اختر صورة» as two full-width buttons.
- **Sending and analysis.** The sending sheet turns the summoning circle while the photo travels. On the scan screen, until the verdict, the circle turns where the photo will be under a sweep of light; on a phone the panel (title, honest stages, results) is a glass card rising from the photo's foot.
- **Type scale.** Page title `text-title` 28 px, from tablet `text-title-lg` 32 px; display section heading `text-heading` 24 px (the smallest size of Reem Kufi); interface section heading `text-subheading` 20 px; body 17 px. Quran and hadith sizes are not part of the scale and did not change.
- **The analysis on a wide screen (5 October 2026, owners).** From tablet up the reader's photo sits whole in a frame of its own proportions, as large as the stage allows (`min(width, height × ratio)` through container units), instead of filling the column cropped and enlarged; and the analysis is a full-screen view like the world (decision 59): no site footer under it from tablet up, so nothing scrolls just to reach one. On a phone it is unchanged. The light sweep over the photo is a soft pass (a quarter of the earlier tint, a fainter and slower band).
- **One scroller.** Beside a photo (scene, analysis, camera discovery) or a map (atlas, place), the panel flows with the page and the photo or the map is pinned under the top bar; no panel scrolls inside itself.

### Game feel: a AAA, Final Fantasy–grade experience (added 4 October 2026)

The owners' target: TABSIRA must feel like a AAA game production — gamified, immersive, cinematic — applied to a social network of meanings, and visibly better than the earlier prototype, whose look («Final Fantasy with a noble cause»: Islamic geometry, gold light, honest game feel) is the starting point. Direction C and the light theme stay the colour systems; this section sets the craft level.

- **Menus and panels like a AAA RPG.** Glass windows with a thin gold double rule and corner ornaments drawn from eight-point khatam geometry; a soft inner glow; titles in Reem Kufi with generous tracking; a luminous selection cursor (a small eight-point star) that moves to the focused item on keyboard and touch focus — never on hover alone.
- **Living backgrounds.** The earlier prototype's Backdrop (aurora + geometric pattern + light motes) becomes a layered, parallax-free scene per screen: night aurora in dark, dawn aurora in light, khatam tilings (8-, 12- and 6-point variants) at very low opacity, slow motes. Under 4 ms per frame on a mid-range phone; everything stops under reduced motion.
- **Cinematic moments with a clear peak and a good end (Peak–End rule).** The scan is a short "summoning": the photo is scanned by a light sweep, StageOrbit gains a glyph per honest stage, the result arrives with a seal. Opening an insight plays the evidence reveal: the Quran and Sunnah panels enter from both sides and a thin gold thread draws between them. «تمّ» triggers the victory banner «اكتُشِف المعنى», a burst, and the fog lifting from the new place in the world (VISUAL-EFFECTS items 3–5 and 9 from the earlier prototype).
- **Quest language without false claims.** QuestLog for the stages and the daily quest, practice ranks (ناظر → متأمّل → مستبصر → بصير بالتمرين), badges, streak, the sky of meanings and the atlas growth, all exactly under the earlier prototype's `GAMIFICATION.md` §0 rules: practice, never piety; rules, never a model; nothing new claimed about scripture; quiet by default; never leaderboards, comparisons, loss-aversion or reward claims. The practice disclaimer is visible wherever a rank or badge appears.
- **Social network as a guild hall, not a ranking.** «تبصرة تواصل» shows posts as illuminated cards (photo, insight title, the verified pair behind a reveal), reactions as two gentle marks, «انتفعتُ بها» and «جزاك الله خيرًا» (decision 61), follows as companions on the path. No counters that turn people into scores.
- **Typography and scripture stay sacred.** No effect ever animates, distorts, glows behind or overlaps Quran or hadith text beyond the calm entrance of its panel; the text is always fully legible, still and selectable.
- **Quality bar.** Every screen is reviewed at 375, 768 and 1440 px in both themes before it is called done; screenshots go to `docs/screenshots/`.

### Landing: the opening scene (added 5 October 2026)

The owners asked for the landing page to feel immersive, in the spirit of the game-feel section above. On first paint it plays one short scene: a khatam turns slowly behind the hero, two glows drift and gold dust rises; the kicker's thread draws, the title's words rise one by one and its gold line catches the light; the phone lands, its two rings open with a bead of light riding each, a band of light scans the rain scene twice, the insight point appears and breathes a ring, its card rises, and the two side cards drift a little, then rest. The capture call sends out a ring of light three times. Further down, each section rises as it comes into view (`useReveal`): eyebrow threads draw, the three steps arrive in turn with a gold thread over each, the story photos settle into their frames, the closing call has its own turning khatam. Nothing is hidden without a script, with motion off (device or «ملفي»), or when already on screen at first paint; hover moves nothing; the example's verses and hadith never move (only the section's heading rises).

### «كفالة بصيرة» (added 5 October 2026)

How the sponsoring screens (decision 60, task 21.2) apply the direction above; nothing new is chosen.

- **A quiet offer, not a call to action.** On the atlas and in the camera discovery, «بصائر تنتظر من يكفلها» is one calm section below the results, in the same glass list rows as the entries around it (Common Region, Similarity). It draws nothing when there is nothing to offer, and no badge, counter or highlight pulls the eye to it (Von Restorff is kept for the primary action of each screen).
- **Place before person.** Each row shows the title, the widened place and its precision label, never an author. The same anonymity holds on the entry page: no author line at all, not an "unknown" one.
- **One primary action per state.** On the entry page the section «كفالة البصيرة» holds a single primary button, «اكفل هذه البصيرة», in the reading column; a guest or an unverified account sees the missing step instead (tajriba §8), and a member without a public identity sees the identity form in place, as the publish screens do.
- **The sponsor's words are labelled as theirs.** The reflection sits in a quoted block marked «تأمّل الكافل», with the note that it is not Quran or hadith; it is plain text, never styled as scripture, and no verse or hadith is placed on these screens.
- **A heavy action asks first.** «إنهاء الكفالة» is a ghost button that opens the usual bottom sheet with the consequence in one sentence (the reflection goes, the place stays wide) and a confirm button next to «تراجع» (tajriba §10, Fitts). The reflection form is a labelled field with a character count and the status the server reports, in words and not colour alone. The sponsor's published reflection can be reported by other signed-in members with the usual report sheet.
- **No game layer here.** The «Game feel» section's ranks, badges, streaks and burst do not apply to sponsoring: no points, counts of sponsorships, rankings or reward wording. «كفالاتي» is a plain list of the current sponsorships under the scope choice beside «بصائري المنشورة».
- **Motion.** Only what the shared sheet and notices already do on display; nothing moves on hover, and it all stops under reduced motion.
- **Privacy on the wire.** The offer asks the server with the map's centre or the camera's centre snapped to the 0.05° grid, and never asks the device for its position on its own account.

### Atlas pin (added 5 October 2026)

The owners chose pin «A» of three drawn for TABSIRA: the familiar pin shape, an emerald drop in a gold rim with the eight-point khatam inside and a small shadow on the ground. Every published insight on the map stands on its tip as this pin; the chosen one is the same pin a third larger with a gold glow at its foot; the point a reader places when publishing uses it too. Clusters stay emerald discs in a gold ring. The pin keeps its own emerald and gold in both themes. It is drawn in code on a canvas (`apps/web/src/components/atlas/map-pin.ts`) at twice its size and handed to MapLibre as an image, so no file or third-party asset is fetched; where no canvas can draw, the map keeps its circles.

### Logo (added 4 October 2026)

The designer's logo (`brand/`) replaces the temporary eight-point star mark and the typed wordmark everywhere: the round calligraphic «تبصرة» is the mark, and «TABSIRA» joins it in the full logo. On night surfaces it is brand gold `#B28B38` (5.99:1); on day surfaces it is deep gold `#8D6E2C` (4.53:1), because brand gold reaches only 3.00:1 on the day background. Favicon, PWA, Apple touch and tile icons carry their own night background with the brand gold mark, so they read on any browser chrome. See `brand/README.md`.

### World: one picture under clouds (added 5 October 2026)

The owners' world design kit replaces the fog map of «Structure» and «Responsive web application» for `/world` (decision 59). The world is one landscape picture (`apps/web/public/world/landscape-1.webp`, 1536 × 1024) under an opaque layer of clouds (`clouds-1.webp`), drawn on a canvas and cut with feathered circles where something was learned. It fills the screen under the top bar, with nothing below it: the site footer's links move into its help panel.

- **A newcomer sees clouds only:** no ground, no region names, no list of regions, no counter; one line, «كلّ بصيرة تفتح أفقًا.», and «اكتشف أول بصيرة», which opens the camera.
- **Controls stay small and screen-sized:** «عالمي» in a pearl card at the start (with the mark on a phone, where there is no top bar); back, help and «بصائري» (once something was learned) as 48 px pearl buttons at the end; zoom in, zoom out and reset in a group at the bottom left (in a row on a short screen), truly disabled at the limits; the call to discover at the bottom centre, above the phone's floating bar.
- **Landmarks:** a 48 px dark green disc with the region's drawing in its theme colour (water `#83e1d5`, planting `#b3d178`, knowledge `#f3d382`, patience `#dacdb8`, kinship `#f2c4b3`, justice `#e3cf9a`) and the region's name in a pearl tag under it; they keep their size whatever the zoom. Only learned regions have one; nothing still under the clouds exists in the page.
- **Panels on request:** a 440–460 px side panel from tablet up, a bottom sheet on a phone, a modal dialog either way; a landmark opens its latest insight (meaning, sources by reference, small step, the day it was learned, «افتح البصيرة», «انتقل إلى موضعها», «حاور بصيرتك») and the others learned there; «بصائري» lists everything learned, the latest first; help explains the world and holds the site's pages.
- **Motion:** a new reveal plays once, 1.4 s eased out, the landmark arriving as the clouds part, with one accent per theme (a turquoise ripple, a green bloom, a short golden light, a slow stone ring along the way); under reduced motion it is simply there and announced. The camera moves by itself only once, to a new reveal; otherwise only the reader moves it (drag, two-finger pinch, the wheel, the arrows, + and −, Home).
- **Colours:** the kit's (`#0f4c3a`, `#082e25`, `#c6a15b`, `#16302a`, `#f6faf7`, `#dce7e1`), the same by day and night because the picture is; panels follow the app's theme tokens, which are the kit's colours by day.

### Landing page (added 5 October 2026)

The owners' landing prompt replaces the full-screen rain scene at `/` with a landing page in TABSIRA's own colours (decision 7 is met: the owners chose the direction). A deep green hero (`#082e25` to `#0f4c3a`, 28 px corners on desktop) holds the title «انظر إلى العالم / بعين الوحي.» (the second line in gold `#dfbd77`), the lead, the gold «صوّر مشهدًا» and the outlined «جرّب مثالًا», and a still phone picture of the prepared rain scene: markup over the scene's photo, one description for assistive technology, no camera, no fetch and no verse in it. Below it: the three steps; three feature stories with a 3:2 picture each, whose lines and ways in follow the server's `FEATURE_*` flags (a story with nothing switched on is not shown); the prepared example on a pale band (`--landing-band`) with «القرآن» and «السُّنّة» tabs, whose texts come from the API through the insight's own evidence cards; «لماذا تبصرة؟»; questions as disclosures; a closing call; and the footer in three columns on every page. On the home page a visitor's top bar shows the page's sections; an account, and every other page, keep the app's. Phones keep the floating bar and get a small header with a menu of the sections. The capture sheet gains a third way in, «جرّب مثالًا».
