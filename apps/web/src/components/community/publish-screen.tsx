'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { type SubmitEvent, useState } from 'react';
import { signInHref } from '@/account/links';
import { StatusScreen } from '@/components/app/status-screen';
import { CommunityIcon } from '@/components/icons';
import { PageContainer } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { CheckboxField } from '@/components/ui/checkbox-field';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { TextArea } from '@/components/ui/text-area';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { useKeptPhoto } from '@/lib/scan/kept-photo';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { createDraft, editDraft, submitPost } from '@/social/api';
import { postPath } from '@/social/identity';
import { type Post, type PostVisibility, REFLECTION_MAX } from '@/social/types';
import { IdentityForm } from './identity-section';
import { PostCard } from './post-card';

const P = messages.community.publish;
const C = messages.community;

const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;

/** What the guard decided, in the author's words of the API's status; a draft cannot come back from submit. */
function outcomeOf(post: Post): string {
  return post.status === 'rejected' || post.status === 'pending_review'
    ? P.outcome[post.status]
    : P.outcome.published;
}

const VISIBILITIES: readonly { value: PostVisibility; label: string }[] = [
  { value: 'public', label: C.post.visibility.public },
  { value: 'followers', label: C.post.visibility.followers },
];

function problemMessage(result: Failure): string {
  if (result.code === 'INSIGHT_NOT_PUBLISHABLE') {
    return P.notPublishable;
  }
  if (result.code === 'SERVICE_UNAVAILABLE') {
    return P.unavailable;
  }
  if (result.code === 'PUBLIC_IDENTITY_REQUIRED') {
    return P.identityFirst;
  }
  if (result.code === 'INSIGHT_ALREADY_POSTED') {
    return P.alreadyPosted;
  }
  return failureMessage(result);
}

interface DraftFormProps {
  initial?: Post;
  /** The owner's insight kept a photo, so a new draft may offer to show it (v2 §19). */
  photoOffered?: boolean;
  busy: boolean;
  failure: string | null;
  onSubmit: (reflection: string | null, visibility: PostVisibility, photo: boolean) => void;
  onCancel?: () => void;
}

/**
 * The author's words and audience; the insight itself is copied by the API and never edited
 * here. The photo is a choice made once, when the draft is created, off by default, and only
 * for a public post: a post for followers never shows it, so the box is not offered there.
 */
function DraftForm({
  initial,
  photoOffered = false,
  busy,
  failure,
  onSubmit,
  onCancel,
}: Readonly<DraftFormProps>) {
  const [reflection, setReflection] = useState(initial?.reflection?.text ?? '');
  const [visibility, setVisibility] = useState<PostVisibility>(initial?.visibility ?? 'public');
  const [photo, setPhoto] = useState(false);
  const length = Array.from(reflection.trim()).length;
  const offersPhoto = photoOffered && initial === undefined && visibility === 'public';
  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (length > REFLECTION_MAX) {
      return;
    }
    onSubmit(length === 0 ? null : reflection.trim(), visibility, offersPhoto && photo);
  };
  const creatingLabel = busy ? P.creating : P.createDraft;
  const savingLabel = busy ? P.saving : P.saveEdit;
  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <TextArea
        label={P.reflection}
        hint={P.reflectionHint(REFLECTION_MAX)}
        value={reflection}
        onChange={(event) => setReflection(event.target.value)}
        maxChars={REFLECTION_MAX}
        rows={5}
      />
      <ChoiceGroup
        legend={P.visibility}
        hint={P.visibilityHint}
        options={VISIBILITIES}
        value={visibility}
        onChange={setVisibility}
      />
      {offersPhoto ? (
        <CheckboxField label={P.photo} hint={P.photoHint} checked={photo} onChange={setPhoto} />
      ) : null}
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit" size="lg" disabled={busy || length > REFLECTION_MAX}>
          {initial === undefined ? creatingLabel : savingLabel}
        </Button>
        {onCancel === undefined ? null : (
          <Button variant="ghost" size="lg" onClick={onCancel}>
            {P.cancelEdit}
          </Button>
        )}
      </div>
    </form>
  );
}

/**
 * From a verified insight to a post (docs/SOCIAL_NETWORK.md «From an insight
 * to a post»): a draft nobody else sees, a preview of it as readers will see
 * it, then the submit button, which runs the guard and tells the author what happened.
 * A refused post becomes a draft again when edited. The insight is named by
 * `?insight=<id>`, which the insight screen's publish action passes.
 */
export function PublishScreen({
  comments = false,
  atlas = false,
}: Readonly<{
  comments?: boolean;
  /** The atlas feature, read by the server: placing the published insight on the map is offered. */
  atlas?: boolean;
}>) {
  const params = useSearchParams();
  const insightId = params.get('insight');
  const access = useAccess();
  const [post, setPost] = useState<Post | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [withdrawn, setWithdrawn] = useState(false);
  const photoKept = useKeptPhoto(insightId, access === 'member');

  const run = async (
    call: () => Promise<Awaited<ReturnType<typeof createDraft>>>,
    done: string | ((post: Post) => string)
  ) => {
    setBusy(true);
    setFailure(null);
    const result = await call();
    setBusy(false);
    if (result.ok) {
      setPost(result.data);
      setEditing(false);
      setNotice(typeof done === 'string' ? done : done(result.data));
    } else {
      setFailure(problemMessage(result));
    }
  };

  if (insightId === null || !PUBLIC_ID.test(insightId)) {
    return (
      <PageContainer className="pt-[max(28px,env(safe-area-inset-top))] pb-10">
        <StatusScreen
          icon={<CommunityIcon width="28" height="28" />}
          title={P.noInsight.title}
          description={P.noInsight.description}
          className="py-10"
        >
          <LinkButton href="/world" variant="secondary">
            {P.noInsight.world}
          </LinkButton>
        </StatusScreen>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="flex max-w-[48rem] flex-col gap-6 pt-[max(28px,env(safe-area-inset-top))] pb-6 tablet:pb-10">
      <Link
        href="/community"
        className="inline-flex min-h-10 items-center self-start text-link underline-offset-4 hover:underline"
      >
        {C.back}
      </Link>
      <header className="flex flex-col gap-2">
        <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
          {P.title}
        </h1>
        <p className="m-0 text-fg-soft leading-[1.85]">{P.lead}</p>
      </header>

      {access === 'guest' ? (
        <GlassPanel className="flex flex-col items-start gap-3">
          <p className="m-0 text-fg-soft">{P.signIn}</p>
          <LinkButton href={signInHref(`/community/publish?insight=${insightId}`)}>
            {C.signIn}
          </LinkButton>
        </GlassPanel>
      ) : null}
      {access === 'unverified' ? (
        <GlassPanel>
          <p className="m-0 text-fg-soft">{P.verify}</p>
        </GlassPanel>
      ) : null}
      {access === 'no-identity' ? (
        <GlassPanel as="section" aria-label={C.identity.title} className="flex flex-col gap-4">
          <p className="m-0 font-semibold text-fg text-lg">{P.identityFirst}</p>
          <IdentityForm />
        </GlassPanel>
      ) : null}
      {access === 'unknown' ? (
        <p role="status" className="m-0 text-fg-muted">
          {C.loading}
        </p>
      ) : null}

      {access === 'member' && post === null ? (
        <GlassPanel ornate className="tablet:p-7">
          <DraftForm
            photoOffered={photoKept}
            busy={busy}
            failure={failure}
            onSubmit={(reflection, visibility, photo) =>
              void run(() => createDraft({ insightId, reflection, visibility, photo }), P.drafted)
            }
          />
        </GlassPanel>
      ) : null}

      {post !== null && !withdrawn ? (
        <div className="flex flex-col gap-5">
          <div role="status" className="empty:hidden">
            {notice ===
            null ? /* v8 ignore next: a post exists only after a call that set its notice; null only satisfies the type */ null : (
              <Notice tone="success">{notice}</Notice>
            )}
          </div>
          {editing ? (
            <GlassPanel ornate className="tablet:p-7">
              <DraftForm
                initial={post}
                busy={busy}
                failure={failure}
                onCancel={() => setEditing(false)}
                onSubmit={(reflection, visibility) =>
                  void run(() => editDraft(post.id, { reflection, visibility }), P.edited)
                }
              />
            </GlassPanel>
          ) : (
            <>
              <h2 className="m-0 font-semibold text-subheading text-fg">{P.preview}</h2>
              <PostCard
                post={post}
                variant="full"
                comments={comments}
                onChange={setPost}
                onRemoved={() => setWithdrawn(true)}
              />
              {failure === null ? null : (
                <div role="alert">
                  <Notice tone="error">{failure}</Notice>
                </div>
              )}
              <div className="flex flex-wrap gap-2.5">
                {post.status === 'draft' || post.status === 'rejected' ? (
                  <>
                    {/* A refused post is edited first: the edit makes it a draft again, and then it can be sent. */}
                    {post.status === 'draft' ? (
                      <Button
                        size="lg"
                        disabled={busy}
                        onClick={() => void run(() => submitPost(post.id), outcomeOf)}
                      >
                        {busy ? P.submitting : P.submit}
                      </Button>
                    ) : null}
                    <Button
                      variant={post.status === 'draft' ? 'secondary' : 'primary'}
                      size="lg"
                      onClick={() => setEditing(true)}
                    >
                      {P.edit}
                    </Button>
                  </>
                ) : (
                  <LinkButton href={postPath(post.id)} size="lg">
                    {P.open}
                  </LinkButton>
                )}
                {/* Decision 68: the map is added on top of the publications, by its own choice. */}
                {atlas && post.status === 'published' ? (
                  <LinkButton
                    href={`/atlas/publish?insight=${insightId}` as Route}
                    variant="secondary"
                    size="lg"
                  >
                    {P.alsoMap}
                  </LinkButton>
                ) : null}
              </div>
            </>
          )}
        </div>
      ) : null}
      {withdrawn ? (
        <div role="status" className="flex flex-col items-start gap-4">
          <Notice tone="success">{P.withdrawn}</Notice>
          <LinkButton href="/community" variant="secondary">
            {C.back}
          </LinkButton>
        </div>
      ) : null}
    </PageContainer>
  );
}
