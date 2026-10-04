# Brand

The TABSIRA logo: the word «تبصرة» in round calligraphy, alone (the mark) or above the Latin name «TABSIRA» (the logo). Masters received on 4 October 2026 as `Logo_no_name.svg` and `Logo_with_name.svg`.

## Files

| File                         | Content            | Colour               | Use                                                              |
| ---------------------------- | ------------------ | -------------------- | ---------------------------------------------------------------- |
| `tabsira-mark.svg`           | the mark           | `currentColor`       | inline in the interface; the colour comes from the theme         |
| `tabsira-mark-gold.svg`      | the mark           | brand gold `#B28B38` | dark backgrounds; source of every icon drawn on the night colour |
| `tabsira-mark-deep-gold.svg` | the mark           | deep gold `#8D6E2C`  | light backgrounds                                                |
| `tabsira-logo.svg`           | mark and «TABSIRA» | `currentColor`       | inline, large sizes                                              |
| `tabsira-logo-gold.svg`      | mark and «TABSIRA» | brand gold           | dark backgrounds, share cards on night                           |
| `tabsira-logo-deep-gold.svg` | mark and «TABSIRA» | deep gold            | light backgrounds, documents                                     |

Every raster (favicon, PWA icons, Apple touch icon, tiles, share cards) is generated from these files by the web app's icon script; none is drawn by hand.

## Colours and contrast

- **Brand gold `#B28B38`** (hue 41°, saturation 52 %, lightness 46 %): 5.99:1 on the night background `#0B1210`, but only 3.00:1 on the day background `#F6FAF7` — on the edge of the 3:1 minimum for graphics (WCAG 2.2, 1.4.11), and below it on any lighter tint.
- **Deep gold `#8D6E2C`**: the same hue and saturation at lightness 36 %: 4.53:1 on `#F6FAF7` and 4.77:1 on white, so the mark stays clear on every light surface, small sizes included.
- The interface therefore shows the mark in brand gold on night and in deep gold on day. Icons that sit on unknown backgrounds (favicon, PWA, Apple touch) carry their own night background with the brand gold mark.

## How these files were made

The original paths are kept exactly as drawn: no point moved, no curve simplified (a raster comparison at 1024 px shows zero differing pixels). Only the document was rewritten: no XML prolog, no editor comment, no layer ids, no class or stylesheet, separators normalised, one fill on the root element and a `<title>` for assistive technology.
