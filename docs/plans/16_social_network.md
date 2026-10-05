# 16 · Social network «تبصرة تواصل»

**Phase:** 2 · **Priority:** Medium · **Status:** 🔄 · **Updated:** 2026-10-04 19:43 (Tunis)

Posts made from verified insights, follows, likes, comments, reports and moderation.

| Step                                                               | Status | Notes                                                                                                                                                                                                    |
| ------------------------------------------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Server side: profiles, posts, feeds, comments, reports, moderation | ✅     | Merged, switched off in production.                                                                                                                                                                      |
| Screens                                                            | ✅     | Task 16.1, screenshots in docs/screenshots (community, post, profile, publish).                                                                                                                          |
| Moderators' queue                                                  | ✅     | Admin queue for posts and comments (task 12.2) and map entries (task 17.2).                                                                                                                              |
| Privacy re-review                                                  | ✅     | Passed for social on 2026-10-04 (`../tabsira-artifact/reviews/privacy-re-review-social-atlas-2026-10-04.md`); its atlas findings 2-7 are task 17.3, finding 1 task 17.2.                                 |
| Share a profile, own page in the top bar                           | ✅     | «شارك صفحتك» on the public profile and in «ملفي» (the phone's share dialog, else the link copied); «صفحتي» in the top bar once a handle is chosen (2026-10-05).                                          |
| Follow from a post or a public insight                             | ✅     | A quiet «تابع» beside the author on every post (the API says `follows_author`, one query per page) and on a public insight's page; always the reader's own tap, never a follow by visiting (2026-10-05). |

**How we check it**

- Re-review before it is switched on.

## Tasks

### 16.1 Social screens

- **Status:** ✅ 2026-10-04 16:51, owners' Wave 4 agent
- **Goal:** Feeds, posts, profiles, comments, reports.
- **Depends on:** Phase 2.
- **Touches:** apps/web community routes.
- **Done when:** Privacy re-review first.
