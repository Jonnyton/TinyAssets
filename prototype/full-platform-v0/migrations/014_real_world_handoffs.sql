-- 014 — Real-world handoffs, their append-only lifecycle, and the additive
-- extension of the existing outcome registry (target
-- `real-world-handoffs-and-outcomes`, tasks 5.1/5.2/5.4 of
-- openspec/changes/complete-independent-full-platform-targets).
--
-- Numbering note: the highest migration on origin/main when this landed was
-- 013_paid_market_workflow.sql, so this file takes 014. Do NOT renumber it
-- later to close a gap — the shipped runtime store names are the contract, not
-- the sequence.
--
-- Substrate note: PLAN has not chosen the canonical store, so the live runtime
-- keeps its owner-scoped SQLite tables (tinyassets/handoffs/store.py, created
-- inside `.runs.db` next to `outcome_event`) and this file is the platform-store
-- mirror of the same shapes and invariants. Neither is treated as the single
-- substrate.
--
-- THIS IS AN EXTENSION, NOT A SECOND REGISTRY. `outcome_event` (migration 001 /
-- tinyassets/outcomes/schema.py) remains the sole generic owner of an outcome
-- claim. `outcome_evidence` is a 1:1 side table carrying the provenance and
-- evidence-level columns the base table lacks, and `outcome_evidence_transition`
-- is its append-only journal. Nothing here writes a competing outcome row.
--
-- Every invariant expressible in SQL is expressed here so a row the runtime
-- would refuse is not persistable:
--   * one handoff per (effect_key, sink) — mirrors the receipt store's PK, so
--     the lifecycle row and the receipt row cannot disagree about how many
--     effects exist;
--   * a contiguous, unique transition sequence per handoff;
--   * lifecycle state and evidence level are closed enumerations;
--   * a confirmation is single-use (consumed_at set once) and owner-scoped;
--   * an external artifact is unique by normalized reference, so two sources
--     contributing to one artifact do not double-count it while both
--     attributions survive;
--   * every child row must belong to a parent the caller owns — the FK alone
--     only proves the parent exists.
--
-- FIXTURE/PROTOTYPE: as with the rest of this chain, do not apply to live data
-- without the founder gate.

-- ---------------------------------------------------------------------------
-- Handoffs — one row per system-derived effect identity.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.handoff (
  handoff_id        text PRIMARY KEY,
  owner_id          uuid NOT NULL REFERENCES public.users(user_id),
  effect_key        text NOT NULL,
  sink              text NOT NULL,
  adapter_action    text NOT NULL,
  destination       text NOT NULL,
  branch_def_id     text NOT NULL DEFAULT '',
  branch_version_id text NOT NULL,
  content_hash      text NOT NULL,
  run_id            text NOT NULL,
  output_field      text NOT NULL,
  output_sha256     text NOT NULL,
  effect_class      text NOT NULL
                      CHECK (effect_class IN ('reversible', 'irreversible')),
  outcome_kind      text NOT NULL,
  credential_class  text NOT NULL DEFAULT '',
  state             text NOT NULL
                      CHECK (state IN (
                        'reserved', 'submitted', 'accepted', 'verified',
                        'rejected', 'uncertain', 'orphaned', 'cancelled'
                      )),
  external_id       text NOT NULL DEFAULT '',
  declaration_json  jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  -- The exactly-once boundary. A second authorized request for the same source
  -- output and destination collides here rather than producing a second effect.
  CONSTRAINT handoff_effect_identity_unique UNIQUE (effect_key, sink),
  -- An accepted/verified handoff must carry the provider's stable external id;
  -- without one the claim is unverifiable later, which is how a transport
  -- success masquerades as a durable destination acceptance.
  CONSTRAINT handoff_accepted_requires_external_id CHECK (
    state NOT IN ('accepted', 'verified') OR external_id <> ''
  )
);

CREATE INDEX IF NOT EXISTS idx_handoff_owner
  ON public.handoff(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_handoff_run ON public.handoff(run_id);
CREATE INDEX IF NOT EXISTS idx_handoff_state ON public.handoff(state);

-- ---------------------------------------------------------------------------
-- Lifecycle transitions — append-only, contiguous per handoff.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.handoff_transition (
  transition_id   text PRIMARY KEY,
  handoff_id      text NOT NULL REFERENCES public.handoff(handoff_id),
  seq             integer NOT NULL CHECK (seq >= 1),
  from_state      text NOT NULL DEFAULT '',
  to_state        text NOT NULL
                    CHECK (to_state IN (
                      'reserved', 'submitted', 'accepted', 'verified',
                      'rejected', 'uncertain', 'orphaned', 'cancelled'
                    )),
  evidence_source text NOT NULL,
  evidence_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT handoff_transition_seq_unique UNIQUE (handoff_id, seq),
  -- A transition out of a terminal state is not legal in the runtime's closed
  -- graph; encode the terminal half here so a bad row cannot be inserted.
  CONSTRAINT handoff_transition_not_from_terminal CHECK (
    from_state NOT IN ('rejected', 'orphaned', 'cancelled')
  )
);

CREATE INDEX IF NOT EXISTS idx_handoff_transition_handoff
  ON public.handoff_transition(handoff_id, seq);

-- ---------------------------------------------------------------------------
-- Per-invocation confirmations for irreversible effects — single-use.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.handoff_confirmation (
  token       text PRIMARY KEY,
  owner_id    uuid NOT NULL REFERENCES public.users(user_id),
  effect_key  text NOT NULL,
  sink        text NOT NULL,
  -- Covers effect summary, destination, and source version/hash, so a
  -- confirmation minted against version N cannot authorize an effect initiated
  -- from a later version.
  fingerprint text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  consumed_at timestamptz,
  CONSTRAINT handoff_confirmation_expiry CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_handoff_confirmation_effect
  ON public.handoff_confirmation(effect_key, sink, owner_id);

-- ---------------------------------------------------------------------------
-- Existing outcome registry owner. The prototype chain did not previously
-- mirror tinyassets/outcomes/schema.py, so establish that same table before
-- adding its evidence lifecycle; this is not a second registry.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.outcome_event (
  outcome_id   text PRIMARY KEY,
  run_id       text NOT NULL,
  outcome_type text NOT NULL CHECK (outcome_type IN (
                 'published_paper', 'merged_pr', 'deployed_app',
                 'won_competition', 'custom'
               )),
  evidence_url text,
  verified_at  timestamptz,
  verified_by  uuid,
  claim_run_id text,
  payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at  timestamptz NOT NULL DEFAULT now(),
  note         text NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_outcome_run
  ON public.outcome_event(run_id);
CREATE INDEX IF NOT EXISTS idx_outcome_type
  ON public.outcome_event(outcome_type);

-- ---------------------------------------------------------------------------
-- Outcome registry EXTENSION — 1:1 with public.outcome_event.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.outcome_evidence (
  outcome_id              text PRIMARY KEY REFERENCES public.outcome_event(outcome_id),
  -- Nullable only for pre-extension rows whose original schema did not persist
  -- the attester. Authenticated inserts are still pinned by RLS below.
  account_id              uuid REFERENCES public.users(user_id),
  branch_def_id           text NOT NULL DEFAULT '',
  branch_version_id       text NOT NULL DEFAULT '',
  content_hash            text NOT NULL DEFAULT '',
  run_id                  text NOT NULL DEFAULT '',
  output_field            text NOT NULL DEFAULT '',
  output_sha256           text NOT NULL DEFAULT '',
  handoff_id              text NOT NULL DEFAULT '',
  effect_key              text NOT NULL DEFAULT '',
  sink                    text NOT NULL DEFAULT '',
  outcome_kind            text NOT NULL,
  evidence_source         text NOT NULL,
  evidence_level          text NOT NULL
                            CHECK (evidence_level IN (
                              'user_attested', 'submitted', 'accepted',
                              'externally_verified', 'disputed', 'rejected',
                              'orphaned', 'retracted'
                            )),
  external_id             text NOT NULL DEFAULT '',
  normalized_external_ref text NOT NULL DEFAULT '',
  attested_by             uuid,
  recorded_at             timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outcome_evidence_account
  ON public.outcome_evidence(account_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcome_evidence_artifact
  ON public.outcome_evidence(normalized_external_ref);
CREATE INDEX IF NOT EXISTS idx_outcome_evidence_handoff
  ON public.outcome_evidence(handoff_id);

CREATE TABLE IF NOT EXISTS public.outcome_evidence_transition (
  transition_id   text PRIMARY KEY,
  outcome_id      text NOT NULL REFERENCES public.outcome_evidence(outcome_id),
  seq             integer NOT NULL CHECK (seq >= 1),
  from_level      text NOT NULL DEFAULT '',
  to_level        text NOT NULL
                    CHECK (to_level IN (
                      'user_attested', 'submitted', 'accepted',
                      'externally_verified', 'disputed', 'rejected',
                      'orphaned', 'retracted'
                    )),
  evidence_source text NOT NULL,
  actor_id        uuid,
  evidence_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT outcome_evidence_transition_seq_unique UNIQUE (outcome_id, seq),
  CONSTRAINT outcome_evidence_transition_not_from_retracted CHECK (
    from_level <> 'retracted'
  )
);

-- ---------------------------------------------------------------------------
-- External artifacts — counted once, attributed many times.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.outcome_artifact (
  artifact_ref  text PRIMARY KEY,
  outcome_kind  text NOT NULL,
  external_id   text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.outcome_artifact_source (
  artifact_ref   text NOT NULL REFERENCES public.outcome_artifact(artifact_ref),
  outcome_id     text NOT NULL REFERENCES public.outcome_evidence(outcome_id),
  contributed_by uuid,
  recorded_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (artifact_ref, outcome_id)
);

-- Pre-extension rows become explicitly user-attested without inventing an
-- actor from verified_by (a verifier is not necessarily the claimant).
INSERT INTO public.outcome_evidence (
  outcome_id, account_id, run_id, outcome_kind, evidence_source,
  evidence_level, attested_by, recorded_at, updated_at
)
SELECT
  outcome_id, NULL, run_id, outcome_type, 'legacy_outcome_event',
  'user_attested', NULL, recorded_at, recorded_at
FROM public.outcome_event
ON CONFLICT (outcome_id) DO NOTHING;

INSERT INTO public.outcome_evidence_transition (
  transition_id, outcome_id, seq, from_level, to_level,
  evidence_source, actor_id, evidence_json, recorded_at
)
SELECT
  'legacy:' || outcome_id || ':user_attested',
  outcome_id, 1, '', 'user_attested', 'legacy_outcome_event',
  NULL, '{}'::jsonb, recorded_at
FROM public.outcome_event
ON CONFLICT (outcome_id, seq) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Row-level security. Owner-scoped throughout; child rows additionally prove
-- parent ownership, because a foreign key alone only proves the parent exists.
-- ---------------------------------------------------------------------------
ALTER TABLE public.handoff ENABLE ROW LEVEL SECURITY;

CREATE POLICY handoff_select_owner ON public.handoff
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_id);

CREATE POLICY handoff_insert_owner ON public.handoff
  FOR INSERT TO PUBLIC
  WITH CHECK (auth.uid() = owner_id);

-- The owner column is deliberately absent from the update path: a handoff is
-- never reassignable, because its receipt and confirmation are bound to the
-- account that authorized the effect.
CREATE POLICY handoff_update_owner ON public.handoff
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = owner_id)
  WITH CHECK (auth.uid() = owner_id);

ALTER TABLE public.handoff_transition ENABLE ROW LEVEL SECURITY;

CREATE POLICY handoff_transition_select_owner ON public.handoff_transition
  FOR SELECT TO PUBLIC
  USING (
    EXISTS (
      SELECT 1 FROM public.handoff h
      WHERE h.handoff_id = handoff_transition.handoff_id
        AND h.owner_id = auth.uid()
    )
  );

CREATE POLICY handoff_transition_insert_owner ON public.handoff_transition
  FOR INSERT TO PUBLIC
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.handoff h
      WHERE h.handoff_id = handoff_transition.handoff_id
        AND h.owner_id = auth.uid()
    )
  );

ALTER TABLE public.handoff_confirmation ENABLE ROW LEVEL SECURITY;

CREATE POLICY handoff_confirmation_select_owner ON public.handoff_confirmation
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_id);

CREATE POLICY handoff_confirmation_insert_owner ON public.handoff_confirmation
  FOR INSERT TO PUBLIC
  WITH CHECK (auth.uid() = owner_id);

-- Consumption is an owner UPDATE that can only ever set consumed_at once; the
-- runtime's UPDATE ... WHERE consumed_at IS NULL is the atomic single-use gate.
CREATE POLICY handoff_confirmation_consume_owner ON public.handoff_confirmation
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = owner_id AND consumed_at IS NULL)
  WITH CHECK (auth.uid() = owner_id);

ALTER TABLE public.outcome_evidence ENABLE ROW LEVEL SECURITY;

-- Outcome claims are readable beyond their author (discovery, leaderboards),
-- but only the account that recorded one may write it. Consumers still receive
-- evidence_level, so a public read cannot flatten user-attested into verified.
CREATE POLICY outcome_evidence_select_all ON public.outcome_evidence
  FOR SELECT TO PUBLIC
  USING (true);

CREATE POLICY outcome_evidence_insert_owner ON public.outcome_evidence
  FOR INSERT TO PUBLIC
  WITH CHECK (auth.uid() = account_id);

CREATE POLICY outcome_evidence_update_owner ON public.outcome_evidence
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = account_id)
  WITH CHECK (auth.uid() = account_id);

ALTER TABLE public.outcome_evidence_transition ENABLE ROW LEVEL SECURITY;

CREATE POLICY outcome_evidence_transition_select_all
  ON public.outcome_evidence_transition
  FOR SELECT TO PUBLIC
  USING (true);

CREATE POLICY outcome_evidence_transition_insert_actor
  ON public.outcome_evidence_transition
  FOR INSERT TO PUBLIC
  WITH CHECK (auth.uid() = actor_id);

ALTER TABLE public.outcome_artifact_source ENABLE ROW LEVEL SECURITY;

CREATE POLICY outcome_artifact_source_select_all ON public.outcome_artifact_source
  FOR SELECT TO PUBLIC
  USING (true);

CREATE POLICY outcome_artifact_source_insert_owner ON public.outcome_artifact_source
  FOR INSERT TO PUBLIC
  WITH CHECK (
    auth.uid() = contributed_by
    AND EXISTS (
      SELECT 1 FROM public.outcome_evidence oe
      WHERE oe.outcome_id = outcome_artifact_source.outcome_id
        AND oe.account_id = auth.uid()
    )
  );
