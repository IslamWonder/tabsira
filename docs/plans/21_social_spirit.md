# 21 · An Islamic spirit for «تبصرة تواصل»

**Phase:** 2 · **Priority:** Medium · **Status:** ⬜ · **Updated:** 2026-10-05 08:47 (Tunis)

The social network leans on acts with a meaning in Islam: sponsoring an insight nobody looks after (decision 60), giving an insight as a gift, and reactions that say something (decision 61).

| Step                                          | Status | Notes                                            |
| --------------------------------------------- | ------ | ------------------------------------------------ |
| «كفالة بصيرة»: orphaned atlas entries         | ⬜     | Task 21.1 (server), 21.2 (screens). Decision 60. |
| Reactions «انتفعتُ بها» and «جزاك الله خيرًا» | ⬜     | Task 21.3. Decision 61.                          |
| «أهدِ بصيرة»: giving an insight               | ⏸      | Task 21.4, a plan only until the owners decide.  |

**How we check it**

- An orphaned entry's public answers carry the widened place and no handle; the earlier cell never reaches a public API again (tested).
- The orphan job run twice on the same day changes nothing the second time (tested).
- No sponsoring, gift or reaction screen shows points, a level or a promise of reward.
- Any verse or hadith on these screens comes from the store by id and matches its hash (tested).

## Tasks

### 21.1 Orphaned entries and sponsoring, server side

- **Status:** ⬜ open
- **Goal:** `MapEntryStatus.ORPHANED`; a "last sign of life" time on the entry (the author's edit or re-placing, a sponsor's reflection, a sponsorship); `python -m src.cli.mark_orphans` for a daily systemd timer on one host, which turns published, unsponsored entries quiet for `ORPHAN_AFTER_DAYS` (30) into `orphaned`, widens their public point to the centre of their admin area (city or region) and drops the handle from public answers; a `map_entry_generalisations` table recording each widening (entry, earlier cell size and label, new level and label, reason, time); `map_entry_sponsorships` (entry, sponsor, started, ended) with one open sponsorship per entry; `POST`/`DELETE /atlas/entries/{id}/sponsorship`; the sponsor's one reflection, moderated like a comment; `GET /atlas/orphans?near=` at the widened places only.
- **Depends on:** 17.3.
- **Touches:** apps/api/src/{models/atlas.py,services/atlas_service.py,routers/atlas.py,cli/mark_orphans.py,config.py}, a migration in the app chain, deploy/ (the timer), .env.example, deploy/env.production.example, the terms and privacy text (widening, sponsor's name shown), docs/PRIVACY.md, the generated web client.
- **Done when:** A widened entry never answers with its earlier cell anywhere; blocks apply to sponsors; an account under 13 cannot sponsor; the job is idempotent.
- **Reviews:** privacy review before merge (location, public identity); decision 42's exception applies, tests in the same commit.
- **Waiting on the owners:** what counts as a sign of life beyond the list above (views do not, so nothing is tracked about readers).

### 21.2 Sponsoring screens

- **Status:** ⬜ open
- **Goal:** Orphaned entries suggested on the atlas and the camera discovery («بصيرة تنتظر من يكفلها»), the «اكفل هذه البصيرة» action, «في كفالة فلان» on the entry, the sponsor's reflection, and «كفالاتي» in the member's own entries.
- **Depends on:** 21.1, a design pass recorded in docs/DESIGN_DECISION.md.
- **Touches:** apps/web/src/{app/atlas,components/atlas,components/camera,messages}.
- **Done when:** The screens follow tajriba.md; nothing scores or ranks sponsors.

### 21.3 Reactions with a meaning

- **Status:** ⬜ open
- **Goal:** Replace `post_likes` with `post_reactions` (post, member, kind `benefited` | `jazak`, time; one of each per member and post); move every existing like to `benefited` in the migration; feeds and posts answer both counts and the reader's own reactions; the «لك» feed ranks on them as it did on likes; the post screen shows «انتفعتُ بها» and «جزاك الله خيرًا» with their counts.
- **Depends on:** 16.1.
- **Touches:** apps/api/src/{models/social.py,services/post_service.py,services/feed_service.py,routers/posts.py}, a migration in the app chain, apps/web community components and messages, the generated web client, the terms if they name likes.
- **Done when:** No «like» or «أثر» is left in the API or the interface; account deletion removes a member's reactions.
- **Waiting on the owners:** an API contract change (AGENTS.md, ask first), approved by decision 61.

### 21.4 «أهدِ بصيرة»: giving an insight (plan only)

- **Status:** ⏸ waiting on the owners
- **Idea:** A member gives one of their insights to one member they follow or who follows them, with an optional short note (a few words, moderated). The receiver sees «أهداك فلان بصيرة» and may keep it in their own world. It is a gift of one insight, not a conversation: no reply, no thread, so decision 2's "no direct messages" holds. The interface leads with «هديّة» («تهادوا تحابوا» if shown, from the store by id) and may explain it as «صدقة علم».
- **Questions for the owners:**
  1. «أهدِ» or «تصدّق بها» as the action's name.
  2. Followers only, mutual follows only, or anyone not blocked.
  3. Does a kept gift count as learned in the receiver's world only after their own «تمّ»? (Suggested: yes.)
  4. A daily limit of gifts per member, against spam.
- **Touches when decided:** apps/api social models, services and routers, a migration, notifications, apps/web community and world, the terms and privacy text (a new data flow between members).
