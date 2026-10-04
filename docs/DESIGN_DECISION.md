# Design decision

**Status: decided on 4 October 2026** by Ghazi Triki: direction **C · ليل الأنوار** for structure and the dark theme, with **A's colours for the light theme**. The owners left the remaining UI and UX choices to the implementer; nothing is taken from the challenge's own website.

The three directions are drawn on one canvas, three phone screens each (the rain scene, the insight at full scroll height, the fog world): <https://claude.ai/artifact/E7FYkF4dw4aqzbh4HkM4XW>. The verse (Ar-Rum 30:50) and the hadith (al-Bukhari 1032) in the mockups were filled from the corpora and checked equal to their source, byte for byte.

## What every direction shares

- Arabic, right-to-left, phone first; WCAG 2.2 AA contrast; touch targets of at least 48 px; no motion on hover; the two pulsing calls on the photo stop under reduced motion.
- The rain scene first, marked «مثال موثّق مُعدّ», with exactly two insights in the photo (Hick's law, Choice overload) and one quiet secondary action «أو صوّر مشهدك أنت» (Occam's razor).
- The insight follows `tajriba.md` §6: title and glimpse, «ما ظهر» kept apart from interpretation, the Quran then the Sunnah, each labelled with its reference and «افتح المصدر», the platform's explanation labelled as such, «لماذا ظهر هذا؟», one small step with «أجّل الآن», the chat with its three-question limit, the AI disclosure line, and a single primary «تمّ» in the thumb zone (Fitts's law, Von Restorff effect).
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

Motion on display and on events only, never on hover: the points breathe on first view, the insight sheet rises, the fog lifts from a place after «تمّ». Everything stops under reduced motion. Sound effects are off by default.

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

Kept from the earlier prototype's look: the eight-point star mark beside the gilded wordmark, the soft aurora with a faint geometric pattern behind light-theme pages (it becomes a deep night aurora in dark), slow light motes (never pointer-driven), StageOrbit and QuestLog for progress, the burst on «تمّ», and event-only sound effects, off by default. Not kept: the bottom navigation on wide screens and the narrow centred column on desktop.

Desktop interactions: every action reachable by keyboard with visible focus; hover may change colour or reveal a tooltip but never moves or resizes anything; drag-and-drop has a button equivalent.
