---
status: active
---

# Moderation MVP — Track F

**Date:** 2026-04-18
**Author:** dev (task #36 pre-draft; unblocks track F when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` §8 (moderation + rate limits, host-locked 2026-04-18 Q10 = community-flagged), §14.7 (backstop primitives).
- Memory: `project_q10_q11_q12_resolutions.md` (community-flagged, no age gate, wiki-orphan deletion).
- Memory: `project_collab_model_split.md` (wiki-open for content — moderation is post-hoc, not pre-review).
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` §1 for `users.trust_tier` + `users.interaction_count`.

Track F is the commons' immune system. Community-flagged, volunteer-triaged, host-backstopped. No ML, no CAPTCHA, no pre-review. It stays narrow because it's *supposed* to stay narrow — the 1% paid-market fee + account-age gate + wiki-orphan deletion do most of the work.

---

## 1. Design principles

1. **Users flag. Volunteer mods triage. Admin-pool backstops.** No platform-driven takedowns of legal content.
2. **Auto-soft-hide at threshold, not at single report.** A single bad actor can't take anything down.
3. **Rubric is contributor-owned.** Lives in `TinyAssets/` repo at `docs/moderation_rubric.md`. Editable via PR. Not hardcoded.
4. **Economic disincentive first, human labor second.** Paid-market 1% fee + min-bid + account-age gates absorb most spam without human review.
5. **Appeal is a right, not a favor.** Artifact owner can always escalate to the admin pool.
6. **Mod bias is real.** Two separate mods must independently concur before hard-delete. Soft-hide needs one.
7. **Bus-factor ≥ 2 from day one** (per `project_host_independent_succession.md`). `host_admin` role is **a pool of at least 2 operators**, not a single person. Recruit at minimum one tier-3 co-maintainer pre-launch.

---

## 2. Data model

Three new tables + one ALTER. Cross-refs schema spec #25.

### 2.1 `moderation_flags`

```sql
CREATE TABLE public.moderation_flags (
  flag_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  artifact_id    uuid NOT NULL,
  artifact_kind  text NOT NULL CHECK (artifact_kind IN ('node','goal','branch','comment')),
  flagger_user_id uuid NOT NULL REFERENCES public.users(user_id),
  reason         text NOT NULL CHECK (reason IN (
                   'spam','harassment','illegal_content','misinformation',
                   'license_violation','credential_leak','other')),
  detail         text,                   -- optional free-text, ≤500 chars
  status         text NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open','triaged','dismissed','upheld','escalated')),
  flagged_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (artifact_id, artifact_kind, flagger_user_id)  -- one flag per user per artifact
);

CREATE INDEX mf_artifact ON public.moderation_flags (artifact_id, artifact_kind);
CREATE INDEX mf_status   ON public.moderation_flags (status) WHERE status = 'open';
```

**Invariant:** `UNIQUE (artifact_id, artifact_kind, flagger_user_id)` prevents one user from manufacturing an auto-soft-hide by flagging N times.

### 2.2 `moderation_decisions`

```sql
CREATE TABLE public.moderation_decisions (
  decision_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  flag_id        uuid NOT NULL REFERENCES public.moderation_flags(flag_id),
  mod_user_id    uuid NOT NULL REFERENCES public.users(user_id),
  action         text NOT NULL CHECK (action IN (
                   'dismissed','upheld_hide','upheld_hard_delete','escalate_to_admin')),
  rationale      text NOT NULL,          -- ≤1000 chars; visible to artifact owner on appeal
  rubric_version text,                   -- which version of moderation_rubric.md applied
  decided_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX md_flag ON public.moderation_decisions (flag_id);
CREATE INDEX md_mod  ON public.moderation_decisions (mod_user_id, decided_at DESC);
```

### 2.3 `moderation_appeals`

```sql
CREATE TABLE public.moderation_appeals (
  appeal_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_id    uuid NOT NULL REFERENCES public.moderation_decisions(decision_id),
  appellant_user_id uuid NOT NULL REFERENCES public.users(user_id),
  message        text NOT NULL,          -- ≤2000 chars
  status         text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','overturned','upheld','dismissed')),
  host_rationale text,                   -- host-admin's resolution note
  filed_at       timestamptz NOT NULL DEFAULT now(),
  resolved_at    timestamptz
);

CREATE INDEX ma_pending ON public.moderation_appeals (status) WHERE status = 'pending';
```

### 2.4 `users` additions

```sql
ALTER TABLE public.users
  ADD COLUMN mod_role        text NOT NULL DEFAULT 'none'
    CHECK (mod_role IN ('none','volunteer','host_admin')),
  ADD COLUMN mod_opted_in_at timestamptz,
  ADD COLUMN flag_accuracy   numeric(5,4);    -- rolling accuracy score, 0-1, null until N flags resolved
```

### 2.5 Artifact-side state

Both `nodes` (and goals, branches, comments analogously) already carry `status` — extend the CHECK:

```sql
ALTER TABLE public.nodes
  DROP CONSTRAINT nodes_status_check,
  ADD CONSTRAINT nodes_status_check CHECK (
    status IN ('draft','published','deprecated','superseded','under_review','hidden')
  );
```

- `under_review` = auto-soft-hidden pending mod decision.
- `hidden` = mod-upheld hide; owner can still see, discovery strips.
- Hard-delete removes the row outright (owner-visible only via `node_activity` audit trail).

---

## 3. Queue state machine

```
artifact                 flags                          decisions            owner view
────────                 ─────                          ─────────            ──────────

status='published'  +  count=0 to N-1 open flags        (no decision)        visible everywhere
                    │
                    │  Nth flag from distinct user
                    ▼
status='under_review' + count=N open flags              (awaiting mod)       visible to owner
                                                                             + owner notified
                    │
                    │  mod A calls resolve_flag
                    ▼
               ┌────┴────┐
               │         │
           dismissed   upheld
               │         │
               ▼         ├── upheld_hide  (1 mod suffices)
         status back     │      ▼
         to published    │  status='hidden'
         + flags closed  │  owner can appeal
                         │
                         └── upheld_hard_delete  (requires 2 concurring mods)
                                ▼
                         row DELETE'd
                         + node_activity audit row stays
                         + owner can appeal to host-admin
                                ▼
                         appeal overturned → row un-deleted from audit
                                             (restores concept; instance_ref was already
                                              owner-local so never touched)

                         appeal upheld → stays deleted
                         host_rationale logged
```

**Key transitions:**

- **Auto-soft-hide threshold** = 3 distinct-flagger flags (`N_auto_hide_threshold` config). Tunable.
- **Hard-delete requires 2-mod concurrence** to reduce single-mod-bias damage. First mod marks `upheld_hard_delete`; artifact transitions to `hidden` + awaits second mod review. Second mod either concurs (row deletes) or overrides (mod disagreement → escalates to host-admin).
- **Appeal is always available** to artifact owner regardless of decision path.

---

## 4. Moderation API (RPCs)

All RPCs are `SECURITY INVOKER` except `resolve_flag` which is `SECURITY DEFINER` (needs to update the underlying artifact's `status` beyond what the flagger role can write).

### 4.1 `flag_content`

```sql
CREATE FUNCTION public.flag_content(
  p_artifact_id   uuid,
  p_artifact_kind text,
  p_reason        text,
  p_detail        text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE
  v_count int;
  v_threshold int;
BEGIN
  -- Account-age gate (§14.7 backstop): can't flag in first 48h
  IF (SELECT account_age_days FROM public.users WHERE user_id = auth.uid()) < 2 THEN
    RAISE EXCEPTION 'account_too_new_to_flag';
  END IF;

  INSERT INTO public.moderation_flags (artifact_id, artifact_kind, flagger_user_id, reason, detail)
  VALUES (p_artifact_id, p_artifact_kind, auth.uid(), p_reason, p_detail);

  -- Check threshold; auto-soft-hide if exceeded.
  SELECT COUNT(*) INTO v_count
  FROM public.moderation_flags
  WHERE artifact_id = p_artifact_id AND artifact_kind = p_artifact_kind AND status = 'open';

  SELECT value_int INTO v_threshold FROM public.mod_config WHERE key = 'N_auto_hide_threshold';
  v_threshold := COALESCE(v_threshold, 3);

  IF v_count >= v_threshold THEN
    PERFORM public._auto_soft_hide(p_artifact_id, p_artifact_kind);
  END IF;

  RETURN jsonb_build_object('flagged', true, 'flag_count', v_count);
END;
$$;
```

### 4.2 `list_review_queue`

```sql
CREATE FUNCTION public.list_review_queue(
  p_filter text DEFAULT 'all',   -- 'all' | 'pending' | 'escalated' | 'my_decisions'
  p_limit  int  DEFAULT 50
) RETURNS TABLE (...) LANGUAGE sql STABLE AS $$
  -- RLS gates: only users with mod_role IN ('volunteer','host_admin') see rows.
  -- Returns: flag + artifact preview + flagger's flag_accuracy + existing mod decisions.
  SELECT ... FROM public.moderation_flags mf
  JOIN public.users u ON u.user_id = mf.flagger_user_id
  WHERE (
    SELECT mod_role FROM public.users WHERE user_id = auth.uid()
  ) IN ('volunteer','host_admin')
  AND mf.status IN ('open','triaged')
  ORDER BY mf.flagged_at ASC
  LIMIT p_limit;
$$;
```

### 4.3 `resolve_flag`

```sql
CREATE FUNCTION public.resolve_flag(
  p_flag_id  uuid,
  p_action   text,                -- 'dismissed' | 'upheld_hide' | 'upheld_hard_delete' | 'escalate_to_admin'
  p_rationale text,
  p_rubric_version text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_flag    record;
  v_mod_role text;
  v_concur_count int;
BEGIN
  SELECT mod_role INTO v_mod_role FROM public.users WHERE user_id = auth.uid();
  IF v_mod_role NOT IN ('volunteer','host_admin') THEN
    RAISE EXCEPTION 'not_a_mod';
  END IF;

  SELECT * INTO v_flag FROM public.moderation_flags WHERE flag_id = p_flag_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'flag_not_found'; END IF;

  INSERT INTO public.moderation_decisions (flag_id, mod_user_id, action, rationale, rubric_version)
  VALUES (p_flag_id, auth.uid(), p_action, p_rationale, p_rubric_version);

  IF p_action = 'dismissed' THEN
    UPDATE public.moderation_flags SET status = 'dismissed' WHERE flag_id = p_flag_id;
    PERFORM public._unhide_if_all_dismissed(v_flag.artifact_id, v_flag.artifact_kind);

  ELSIF p_action = 'upheld_hide' THEN
    PERFORM public._set_artifact_status(v_flag.artifact_id, v_flag.artifact_kind, 'hidden');
    UPDATE public.moderation_flags SET status = 'upheld' WHERE flag_id = p_flag_id;

  ELSIF p_action = 'upheld_hard_delete' THEN
    -- Requires 2 concurring mods for hard delete.
    SELECT COUNT(*) INTO v_concur_count
    FROM public.moderation_decisions
    WHERE flag_id = p_flag_id AND action = 'upheld_hard_delete' AND mod_user_id != auth.uid();

    IF v_concur_count >= 1 THEN
      -- 2nd concur: proceed with hard delete.
      PERFORM public._hard_delete_artifact(v_flag.artifact_id, v_flag.artifact_kind);
      UPDATE public.moderation_flags SET status = 'upheld' WHERE flag_id = p_flag_id;
    ELSE
      -- 1st hard-delete vote: soft-hide pending concurrence; mark flag triaged.
      PERFORM public._set_artifact_status(v_flag.artifact_id, v_flag.artifact_kind, 'hidden');
      UPDATE public.moderation_flags SET status = 'triaged' WHERE flag_id = p_flag_id;
    END IF;

  ELSIF p_action = 'escalate_to_admin' THEN
    UPDATE public.moderation_flags SET status = 'escalated' WHERE flag_id = p_flag_id;
  END IF;

  RETURN jsonb_build_object('resolved', true, 'action', p_action);
END;
$$;
```

### 4.4 `appeal_decision`

Artifact owner → host-admin queue. One per decision.

```sql
CREATE FUNCTION public.appeal_decision(
  p_decision_id uuid,
  p_message     text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE
  v_artifact_owner uuid;
BEGIN
  -- Load the target artifact's owner; caller must match.
  SELECT public._artifact_owner(v_dec.artifact_id, v_dec.artifact_kind) INTO v_artifact_owner
  FROM public.moderation_decisions v_dec WHERE v_dec.decision_id = p_decision_id;

  IF v_artifact_owner != auth.uid() THEN
    RAISE EXCEPTION 'not_artifact_owner';
  END IF;

  INSERT INTO public.moderation_appeals (decision_id, appellant_user_id, message)
  VALUES (p_decision_id, auth.uid(), p_message);

  RETURN jsonb_build_object('appeal_filed', true);
END;
$$;
```

### 4.5 `resolve_appeal` (admin-pool)

Any user with `mod_role='host_admin'` can resolve. Admin-pool member overrides or upholds the prior mod decision. Standard pattern. **Recusal rule:** an admin cannot resolve an appeal on an artifact they own, nor one where they were the original mod whose decision is being appealed.

Bus-factor-2 property: at least 2 admins exist, and any can handle any appeal (minus own-artifact / own-decision recusal). If host goes offline, the platform's appeals queue continues to drain through the co-maintainer(s).

---

## 5. Tier-gated mod powers + rep threshold

### 5.1 Who can flag

Anyone with `account_age_days >= 2`. Prevents drive-by sybil flags.

### 5.2 Who can triage

| Tier | Default mod_role | How to upgrade |
|---|---|---|
| T1 chatbot | `none` | Upgrade to T2 then earn rep (see below). |
| T2 daemon host | `none` until earned | **Threshold metric (see §5.3)**. |
| T3 contributor | `volunteer` by default | One-time acceptance of CONTRIBUTING.md + `moderation_rubric.md`. Signals via PR comment or the `/account` UI. Tier-3 status comes from having a merged PR to `TinyAssets/`. |
| Admin pool (≥2 operators) | `host_admin` | Launch seed: host (Jonathan) + at least one tier-3 co-maintainer recruited pre-launch (per succession memory). New admins added via existing-admin-pool 2-of-N approval. Not permanent; can be rotated. |

### 5.3 Tier-2 → volunteer mod earn threshold (pick one)

Candidate metrics:

| Metric | Pro | Con |
|---|---|---|
| **(a) N=20 fulfilled paid requests + M=4 weeks reliable hosting** | Ties rep to actual contribution; measurable from Postgres | 4 weeks is slow to earn at launch |
| **(b) Flag-accuracy score ≥ 0.75 over 10+ flags** | Directly selects for flag judgment | Bootstrap problem — how do users build history if they can't triage? |
| **(c) Community vote — existing mods nominate** | High-signal | Slow + political; small-set risk |

**Pick (a).** Reasoning:
- Only T2-earn path; gates on *verified work done for the commons*, not gameable.
- 20 paid requests @ ~1/day = ~3 weeks → ~4-week threshold is organic pacing.
- Tracks uptime + reliability, not just volume.
- Opt-in: user must call `accept_mod_role` + read rubric after hitting the metric. Not auto-granted.

**Opt-in RPC:**
```sql
CREATE FUNCTION public.accept_mod_role() RETURNS jsonb ...
  -- Checks the metric, requires explicit accept of current rubric_version,
  -- flips mod_role from 'none' to 'volunteer'.
```

### 5.4 Flag-accuracy score (rep-maintenance)

Rolling metric: `(upheld flags filed by this user) / (resolved flags filed by this user)`. Updated by trigger on `moderation_flags.status` transitioning out of `open`.

- **Score < 0.25 over last 20 flags** → auto-demote to `mod_role='none'` + notify user. "Your recent flags haven't matched community consensus; step back and re-read the rubric."
- Not a ban. User can re-earn via future accurate flags.
- Prevents false-flag brigading at the cost of one extra column.

---

## 6. Rubric first-draft

`docs/moderation_rubric.md` lives in `TinyAssets/` repo, editable via PR. First-draft content:

```markdown
# Moderation Rubric v1.0

Community-flagged moderation. This rubric is what volunteer mods use to
resolve flags. Rubric changes happen via PR; previously-decided flags
are NOT retroactively reviewed when the rubric updates.

## What to uphold

Flag upheld if the artifact meets ANY of:

1. **Illegal under US federal law** (the platform's jurisdiction at launch).
2. **Contains credentials or private instance data that leaked into the concept layer**
   — e.g. API keys, passwords, live financial account numbers, personal addresses
   of non-consenting parties. Hide (not hard-delete); let owner privatize or redact.
3. **Spam** — identical-text artifacts posted en masse, off-topic commercial
   advertisement, linkjacking to unrelated sites. Hide for individual artifacts;
   hard-delete only for bulk-spam accounts.
4. **Harassment or doxxing** — targeted abuse of an identifiable individual.
5. **License violation** — artifact claims a license incompatible with the
   repo's CC0-1.0, OR imports copyrighted work without permission.

## What to dismiss

1. Disagreement about quality, style, or usefulness (not a mod concern).
2. Flags on artifacts that have been revised since the flag — re-review the
   current state; old state is audit-trail only.
3. Flags motivated by dispute with the artifact owner on an unrelated matter.
4. Content that is legally protected speech in the US, even if unpleasant.

## Hard-delete threshold

Hard-delete is reserved for:
- Illegal content (CSAM, doxxing with identifiable PII, credible threats).
- Persistent bulk spam after hide hasn't stopped it.
- Credential leaks that remain after owner was given a chance to redact.

Hide is the default upheld action. Hard-delete requires 2 concurring mods.

## Rationale requirement

Every `resolve_flag` call requires a rationale ≥20 characters. The rationale
is visible to the artifact owner on appeal. Write as if the owner will read it.
```

Subsequent rubric changes come via PR with 2 admin-pool members approving. No single-person veto (bus-factor ≥ 2 per succession memory) — a lone admin can't block a 2-admin majority on rubric changes.

---

## 7. Abuse defenses

### 7.1 False-flag brigading

Coordinated N accounts flag artifact X to auto-soft-hide it.

Defenses (layered):
1. **Account-age gate (§4.1):** first 48h can't flag.
2. **Unique-flagger-per-artifact constraint (§2.1):** N sock puppets still need N distinct accounts.
3. **Flag-accuracy rolling score (§5.4):** brigading accounts tend to file low-accuracy flags; score drops fast, mod_role revoked, flags de-prioritized in the queue.
4. **Owner-visible "N flags pending" count on the artifact's `/catalog` page:** transparency itself deters brigading because it's observable.

### 7.2 Retaliation after mod decision

Mod dismisses a flag; dismissed flagger creates new accounts or flag other artifacts the mod owns.

Defenses:
1. **Mod-own-artifact recusal:** `resolve_flag` RPC checks `v_flag.artifact_owner != auth.uid()`. Mods cannot resolve flags on their own artifacts.
2. **Appeal path** routes to host-admin, not the same mod.
3. **Cross-mod accountability:** hard-delete requires 2 concurring mods. One retaliatory mod can't single-handedly delete an enemy's artifact.

### 7.3 Mod bias

A mod systematically upholds/dismisses based on who the author is, what domain, etc.

Defenses:
1. **Public mod-decision log:** `moderation_decisions` is readable by everyone (RLS allow-all on SELECT) — enables community oversight.
2. **Rationale requirement ≥20 chars:** encourages reasoned decisions, creates paper trail.
3. **Host-admin review of contested patterns:** periodic audit (manual at MVP) of mods with high hard-delete ratios or skewed outcomes.
4. **Opt-in path + re-reading rubric every 30 days:** mods re-accept the current `rubric_version` periodically; bounces those who've disengaged.

### 7.4 Pre-emptive self-hide harassment

User flags their own artifact via sock-puppet to frame "I was falsely flagged" narrative.

Mostly self-limiting: sock puppets are flagged as low-accuracy quickly, the "victim" owner's appeal gets routed based on the merit of the artifact not the narrative. No special code needed.

---

## 8. Rate limits + economic disincentives

Per §14.7 backstop + memory `project_q10_q11_q12_resolutions.md`:

- **Flag rate limit:** max 10 flags/hour per user (Upstash Redis bucket, reset hourly).
- **Artifact creation rate limit:** max 30 `update_node` or `create_node` calls/minute per user.
- **Bid rate limit:** max 20 paid requests/hour per user (per #29 §7.1).
- **Paid-market 1% fee:** sign-extension of moderation. Pure-spammers can't extract value from the commons; 1% on any bids they place becomes a tax on the attack.
- **Min-bid threshold + account-age gate on bids:** same (#29 §7.1 covers).

---

## 9. Honest dev-day estimate

Navigator's §10 estimate: **~0.75 d** (track F base 0.5d + §14.7 backstop +0.25d).

My build-out:

| Work item | Estimate |
|---|---|
| Schema: 3 tables (flags/decisions/appeals) + `users` ALTER + `nodes` status CHECK extension | 0.25 d |
| RPCs: `flag_content`, `list_review_queue`, `resolve_flag`, `appeal_decision`, `resolve_appeal`, `accept_mod_role` | 0.5 d |
| Helper functions: `_auto_soft_hide`, `_unhide_if_all_dismissed`, `_set_artifact_status`, `_hard_delete_artifact`, `_artifact_owner` | 0.25 d |
| Flag-accuracy trigger + rolling-window math + auto-demote logic | 0.2 d |
| RLS policies — review queue gated on mod_role; decisions readable by all; appeals owner+host-admin | 0.2 d |
| Rate-limit integration (Upstash bucket or Postgres-trigger) for flags + account-age gate | 0.15 d |
| Rubric file: `docs/moderation_rubric.md` initial content + PR-review process doc | 0.1 d |
| Tests: flag → auto-hide, resolve → dismiss, 2-mod hard-delete concur, appeal round-trip, mod-recusal, flag-accuracy demote | 0.3 d |
| Docs: moderation runbook for host-admin + mod onboarding guide | 0.1 d |
| **Total** | **~2.05 d** |

**Revision: 0.75 d → ~2 d.** Navigator's 0.75d was the simplest-case sketch. Honest scope includes 2-mod-concurrence for hard-delete (design rigor), flag-accuracy trigger (abuse defense), appeal RPC (right-not-favor), and rate-limit integration. All are load-bearing.

**Defer paths:**
- **Ship without flag-accuracy auto-demote** = −0.2d. Abuse-brigading gets worse; manual host-admin cleanup until added.
- **Ship with 1-mod hard-delete** (skip 2-mod concur) = −0.15d. Single mod bias enough to destroy artifacts. Recommend against.
- **Ship without appeal RPC** (route appeals through GitHub issues instead) = −0.2d. Acceptable at very early launch volume.

**Recommend full ~2 d.** Skipping 2-mod-concur or appeals undermines the community-flagged philosophy — the backstop primitives ARE the design.

**Session revision tally update:** +17d across 8 revisions (25:+0, 26:+2, 27:+1, 29:+3, 30:+2.5, 32:+3, 34:+3.5, 36:+1.25). §10 8.5-10.5 → ~25-27 with 2 devs at full scope.

---

## 10. OPEN flags

| # | Question |
|---|---|
| Q1 | `N_auto_hide_threshold` default — 3 is conservative. 2 = snappier but more brigade-vulnerable; 5 = slower to act. Recommend 3 + make tunable per-artifact-kind (comments could be N=2). |
| Q2 | Tier-2 earn threshold — 20 paid requests + 4 weeks is my pick per §5.3. Host confirm vs alternate metric. |
| Q3 | Flag-accuracy demote threshold — 0.25 over 20 flags is aggressive; 0.15 over 30 flags is gentler. First number picks who gets hit first. |
| Q4 | Mod-rotation cadence — "re-accept current rubric_version every 30 days" vs "re-accept on every rubric_version change." 30-day cadence catches disengaged mods; version-tied catches rubric-disagreement. Recommend version-tied; mods who don't accept a version stay on previous version until they do. |
| Q5 | Public moderation-decisions log — fully public or mod-only readable? Public transparency vs privacy for flagger identity. Recommend public for decision metadata (action + rationale + rubric_version); flagger identity kept to mods only. |
| Q6 | Comment moderation — this spec covers nodes/goals/branches/comments. Comments have different UX (attached to artifacts, not freestanding). Separate rate limits? Recommend yes; keep comment rate limits looser since comments are higher-volume low-stakes. |
| Q7 | DMCA counter-notice flow — licensed-content takedowns need formal counter-notice handling (US law). Separate from rubric-based moderation. Recommend: out of scope for MVP; route all DMCA to host-admin queue as `reason='illegal_content'` + manual US-law-compliant response. |
| Q8 | Age-gate signals from chatbot provider — memory says we rely transitively (no platform age-gate). Should flagged-content visible to minors (e.g. browse anonymous) be filtered differently? Not MVP; flag for legal review. |

---

## 11. Acceptance criteria

Track F is done when:

1. 4 tables (flags/decisions/appeals + users ALTER + nodes status CHECK) migrate cleanly.
2. 6 RPCs land + ruff-clean + test-covered.
3. `docs/moderation_rubric.md` merged into `TinyAssets/` repo with CONTRIBUTING note pointing at the PR-review-for-updates process.
4. Smoke test: flag → auto-hide at N=3 → mod dismisses → artifact un-hidden. Round-trip green.
5. Smoke test: flag → mod upheld_hard_delete → 2nd mod concurs → artifact deleted. Owner appeal routes to host-admin queue.
6. Mod-recusal test: mod cannot resolve flag on their own artifact (RPC returns exception).
7. Flag-accuracy demote test: simulated user with 20 flags all dismissed → `mod_role` flipped to `none`, notified.
8. Rate-limit test: 11th flag in the same hour rejected with `rate_limited` error per #27 §4 envelope.
9. All 8 OPEN flags resolved or deferred.

If any fails, track F is not shippable; the commons has no immune system.
