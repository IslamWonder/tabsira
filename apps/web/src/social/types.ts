import type { components } from '@/lib/api/schema';

/*
 * The shapes of the social network, straight from the API's OpenAPI document
 * (AGENTS.md: a type is never written twice). A public id is a string.
 */

type Schemas = components['schemas'];

export type Post = Schemas['PostOut'];
export type PostInsight = Schemas['InsightOut'];
export type QuranEvidence = Schemas['QuranEvidenceOut'];
export type HadithEvidence = Schemas['HadithEvidenceOut'];
export type Reflection = Schemas['ReflectionOut'];
export type Why = Schemas['WhyOut'];
export type PostStatus = Schemas['PostStatus'];
export type PostVisibility = Schemas['PostVisibility'];
export type FeedPage = Schemas['FeedPage'];
export type MyPostsPage = Schemas['MyPostsPage'];
export type EmptyReason = NonNullable<FeedPage['empty_reason']>;
export type Comment = Schemas['CommentOut'];
export type CommentPage = Schemas['CommentPage'];
export type Member = Schemas['MemberOut'];
export type MemberProfile = Schemas['MemberProfileOut'];
export type PublicIdentity = Schemas['PublicIdentityOut'];
export type ReportReason = Schemas['ReportReason'];
export type ReportTarget = Schemas['ReportTarget'];
export type Reaction = Schemas['ReactionOut'];
export type HadithClassification = Schemas['HadithClassification'];

/** The reasons in the order the report sheet offers them; the two place reasons are the atlas's. */
export const REPORT_REASONS: readonly ReportReason[] = [
  'abuse',
  'spam',
  'false_religious_claim',
  'unauthorised_photo',
  'wrong_place',
  'private_information',
  'other',
];

/** The limits the API applies (apps/api/src/models/social.py), repeated for the counters. */
export const REFLECTION_MAX = 800;
export const COMMENT_MAX = 500;
export const REPORT_DETAILS_MAX = 500;
