# Design decision

**Status: pending.** No interface work starts until the owners record a choice below (AGENTS.md, Ask first).

The three directions are drawn on one canvas, three phone screens each (the rain scene, the insight at full scroll height, the fog world): <https://claude.ai/artifact/E7FYkF4dw4aqzbh4HkM4XW>. The verse (Ar-Rum 30:50) and the hadith (al-Bukhari 1032) in the mockups were filled from the corpora and checked equal to their source, byte for byte.

## What every direction shares

- Arabic, right-to-left, phone first; WCAG 2.2 AA contrast; touch targets of at least 48 px; no motion on hover; the two pulsing calls on the photo stop under reduced motion.
- The rain scene first, marked «مثال موثّق مُعدّ», with exactly two insights in the photo (Hick's law, Choice overload) and one quiet secondary action «أو صوّر مشهدك أنت» (Occam's razor).
- The insight follows `tajriba.md` §6: title and glimpse, «ما ظهر» kept apart from interpretation, the Quran then the Sunnah, each labelled with its reference and «افتح المصدر», the platform's explanation labelled as such, «لماذا ظهر هذا؟», one small step with «أجّل الآن», the chat with its three-question limit, the AI disclosure line, and a single primary «تمّ» in the thumb zone (Fitts's law, Von Restorff effect).
- The hadith is shown whole, exactly as stored. The chain of narrators is set smaller and quieter and the Prophet's words stand out; this is presentation only, no character is added or removed. **To confirm by the owners.**
- Five tabs with the camera in the centre: عالمي، تواصل، التقط، الأطلس، ملفي (Jakob's law, Serial position effect).
- The world is a fog map: a place appears where an insight was saved, and a dotted thread joins two places only when a relation is recorded (Zeigarnik effect, Goal-gradient effect without scores).

## The directions

| | A · نهار مزهر | B · مخطوطة مذهّبة | C · ليل الأنوار |
| --- | --- | --- | --- |
| Feeling | Joyful daylight, airy, familiar | Heritage, calm, scholarly | Immersive, contemplative, cinematic |
| Ground | White and mint `#F6FAF7` | Parchment `#F3EBD8` with a hairline lattice | Night `#0B1210` |
| Accents | Emerald `#0F4C3A`, gold `#C6A15B` (text gold `#7A5A1C`) | Emerald, gold leaf `#A8812F`, vermilion rubrics `#9E3324` | Glow emerald `#3FD69A`, light gold `#E6C77F` |
| Type | El Messiri titles, IBM Plex Sans Arabic text, Noto Naskh hadith | Amiri titles and hadith, Markazi Text interface | Reem Kufi titles, Readex Pro text, Noto Naskh hadith |
| Photo | Rounded card, white pills with pins | Mihrab-arch gilded frame, cartouches, eight-point stars | Full bleed, glowing points, dark glass labels |
| Quran | Mint card, Uthmani script | Centred like a mushaf page under a framed heading | Ivory script on a soft gold glow |
| Strength | Clearest and most familiar; the safest for first-time users | The most distinctive and the closest to the subject | The strongest "wow" for the video; photos shine |
| Risk | Can look like many apps | Dense; harder to keep light on small phones | Dark UI is harder for long reading and in daylight |

All three use the KFGQPC Uthmanic Hafs font for the Quran.

## Choice

- Direction: _(to fill: A, B, C, or a combination such as "A with C's full-bleed photo")_
- Hadith display (chain quieter, text whole): _(to confirm)_
- Date and owners:
