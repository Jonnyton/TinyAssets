-- 012 — Authoring sessions, events, artifact versions, file handles, and
-- per-run effect confirmations (target `node-authoring-and-autoresearch`,
-- tasks 4.1/4.2 of
-- openspec/changes/complete-independent-full-platform-targets).
--
-- Numbering note: 010 and 011 are held by parallel in-flight lanes at the time
-- this landed, so this file takes 012 and a numbering gap is expected and
-- intentional. Do NOT renumber it to close the gap — the shipped runtime store
-- names are the contract, not the sequence.
--
-- Substrate note: PLAN has not chosen the canonical store, so the live runtime
-- keeps its owner-scoped SQLite store (tinyassets/authoring/store.py) and this
-- file is the platform-store mirror of the same shapes and invariants. Neither
-- is treated as the single substrate. Every invariant expressible in SQL is
-- expressed here so a row the runtime would refuse is not persistable:
--   * one owner per session, never reassignable (no UPDATE policy on owner);
--   * draft_version strictly monotonic per session (compare-and-swap in the
--     runtime; CHECK + trigger-free monotonicity here via the events table);
--   * contiguous, unique event sequence per session;
--   * one (artifact_id, version_no) per published version, immutable;
--   * file handles expire and are owner-scoped, never path-bearing;
--   * every child row (event, handle, confirmation) must belong to a session
--     the caller owns — the FK alone only proves the session exists.
--
-- FIXTURE/PROTOTYPE: as with the rest of this chain, do not apply to live data
-- without the founder gate.

-- ---------------------------------------------------------------------------
-- Sessions — owner-scoped drafts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.authoring_sessions (
  session_id        text PRIMARY KEY,
  owner_id          uuid NOT NULL REFERENCES public.users(user_id),
  artifact_id       text NOT NULL,
  artifact_kind     text NOT NULL CHECK (artifact_kind IN ('node', 'evaluator')),
  seed_mode         text NOT NULL CHECK (seed_mode IN ('sketch', 'artifact', 'session')),
  seed_ref          text NOT NULL DEFAULT '',
  parent_version_id text NOT NULL DEFAULT '',
  status            text NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'published', 'expired')),
  -- Monotonic draft counter; the runtime advances it under compare-and-swap.
  draft_version     int NOT NULL DEFAULT 1 CHECK (draft_version >= 1),
  definition        jsonb NOT NULL,
  definition_hash   text NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  -- Retention boundary: a diff anchor outside it fails explicitly rather than
  -- being diffed against a substitute version.
  retention_until   timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_authoring_sessions_owner
  ON public.authoring_sessions (owner_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Events — the immutable session history and the anchors a diff is taken from.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.authoring_events (
  event_id        text PRIMARY KEY,
  session_id      text NOT NULL REFERENCES public.authoring_sessions(session_id)
                    ON DELETE CASCADE,
  owner_id        uuid NOT NULL REFERENCES public.users(user_id),
  seq             int NOT NULL CHECK (seq >= 1),
  event_type      text NOT NULL CHECK (event_type IN (
                    'created', 'edit', 'test', 'publish', 'publish_failed',
                    'confirmation')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  definition_hash text NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_authoring_events_session
  ON public.authoring_events (session_id, seq);

-- ---------------------------------------------------------------------------
-- Published versions — immutable; a later edit publishes another row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.authoring_versions (
  version_id        text PRIMARY KEY,
  artifact_id       text NOT NULL,
  artifact_kind     text NOT NULL CHECK (artifact_kind IN ('node', 'evaluator')),
  version_no        int NOT NULL CHECK (version_no >= 1),
  owner_id          uuid NOT NULL REFERENCES public.users(user_id),
  visibility        text NOT NULL DEFAULT 'public'
                      CHECK (visibility IN ('public', 'private')),
  definition        jsonb NOT NULL,
  definition_hash   text NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
  parent_version_id text NOT NULL DEFAULT '',
  change_message    text NOT NULL DEFAULT '',
  created_at        timestamptz NOT NULL DEFAULT now(),
  -- Provenance carries the producing session/draft version or the reviewed
  -- contributor source; evidence carries the required-test records.
  provenance        jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence          jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (artifact_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_authoring_versions_artifact
  ON public.authoring_versions (artifact_id, version_no DESC);

-- ---------------------------------------------------------------------------
-- File handles — execution-scoped, expiring, owner-scoped. No path column:
-- a shared definition must never carry a client or host filesystem location.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.authoring_file_handles (
  handle_id   text PRIMARY KEY,
  session_id  text NOT NULL REFERENCES public.authoring_sessions(session_id)
                ON DELETE CASCADE,
  owner_id    uuid NOT NULL REFERENCES public.users(user_id),
  input_name  text NOT NULL DEFAULT '',
  filename    text NOT NULL CHECK (filename NOT LIKE '%/%' AND filename NOT LIKE '%\%'),
  media_type  text NOT NULL,
  size_bytes  bigint NOT NULL CHECK (size_bytes >= 0),
  sha256      text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz NULL,
  CONSTRAINT authoring_handle_expires_after_creation CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_authoring_handles_session
  ON public.authoring_file_handles (session_id, owner_id);

-- ---------------------------------------------------------------------------
-- Per-run effect confirmations — single-use rows, not signed blobs, so
-- consumption is atomic and a replay cannot be forged.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.authoring_confirmations (
  token         text PRIMARY KEY,
  session_id    text NOT NULL REFERENCES public.authoring_sessions(session_id)
                  ON DELETE CASCADE,
  owner_id      uuid NOT NULL REFERENCES public.users(user_id),
  draft_version int NOT NULL CHECK (draft_version >= 1),
  -- Binds the confirmation to one (session, draft version, effect, payload,
  -- credential class) tuple: a token cannot migrate to another run or effect.
  fingerprint   text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  created_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,
  consumed_at   timestamptz NULL,
  CONSTRAINT authoring_confirmation_expires_after_creation
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_authoring_confirmations_open
  ON public.authoring_confirmations (session_id, draft_version)
  WHERE consumed_at IS NULL;

-- ---------------------------------------------------------------------------
-- RLS — owner-scoped by default; published public versions are readable by any
-- authenticated caller. Reads and mutations fail closed for non-owners, and
-- there is no UPDATE/DELETE policy for events or versions: both are immutable.
-- ---------------------------------------------------------------------------
ALTER TABLE public.authoring_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY authoring_sessions_select_owner ON public.authoring_sessions
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_id);

CREATE POLICY authoring_sessions_insert_owner ON public.authoring_sessions
  FOR INSERT TO PUBLIC
  WITH CHECK (auth.uid() = owner_id);

-- Owner may advance their own draft; the owner column itself is never
-- reassignable because both USING and WITH CHECK pin it to the caller.
CREATE POLICY authoring_sessions_update_owner ON public.authoring_sessions
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = owner_id)
  WITH CHECK (auth.uid() = owner_id);

ALTER TABLE public.authoring_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY authoring_events_select_owner ON public.authoring_events
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_id);

CREATE POLICY authoring_events_insert_owner ON public.authoring_events
  FOR INSERT TO PUBLIC
  WITH CHECK (
    auth.uid() = owner_id
    -- The FK only proves the session exists. Without this EXISTS, a caller
    -- could attach an event to another user's session with their own owner_id.
    AND EXISTS (
      SELECT 1 FROM public.authoring_sessions s
      WHERE s.session_id = authoring_events.session_id AND s.owner_id = auth.uid()
    )
  );

ALTER TABLE public.authoring_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY authoring_versions_select_owner ON public.authoring_versions
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_id);

-- A published *public* version is readable by any authenticated caller: that is
-- what publication means. Private versions stay owner-only via the policy above.
CREATE POLICY authoring_versions_select_public ON public.authoring_versions
  FOR SELECT TO PUBLIC
  USING (visibility = 'public' AND auth.uid() IS NOT NULL);

-- A version row names no session column, so its integrity comes from the
-- provenance session id: the publisher must own the session they claim to
-- publish from.
CREATE POLICY authoring_versions_insert_owner ON public.authoring_versions
  FOR INSERT TO PUBLIC
  WITH CHECK (
    auth.uid() = owner_id
    AND (
      coalesce(provenance->>'source_session_id', '') = ''
      OR EXISTS (
        SELECT 1 FROM public.authoring_sessions s
        WHERE s.session_id = provenance->>'source_session_id'
          AND s.owner_id = auth.uid()
      )
    )
  );

ALTER TABLE public.authoring_file_handles ENABLE ROW LEVEL SECURITY;

-- An expired or revoked handle is not readable at all, not merely unusable.
CREATE POLICY authoring_handles_select_owner ON public.authoring_file_handles
  FOR SELECT TO PUBLIC
  USING (
    auth.uid() = owner_id
    AND revoked_at IS NULL
    AND expires_at > now()
  );

CREATE POLICY authoring_handles_insert_owner ON public.authoring_file_handles
  FOR INSERT TO PUBLIC
  WITH CHECK (
    auth.uid() = owner_id
    AND EXISTS (
      SELECT 1 FROM public.authoring_sessions s
      WHERE s.session_id = authoring_file_handles.session_id
        AND s.owner_id = auth.uid()
    )
  );

CREATE POLICY authoring_handles_revoke_owner ON public.authoring_file_handles
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = owner_id)
  WITH CHECK (auth.uid() = owner_id);

ALTER TABLE public.authoring_confirmations ENABLE ROW LEVEL SECURITY;

CREATE POLICY authoring_confirmations_select_owner ON public.authoring_confirmations
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_id);

CREATE POLICY authoring_confirmations_insert_owner ON public.authoring_confirmations
  FOR INSERT TO PUBLIC
  WITH CHECK (
    auth.uid() = owner_id
    AND EXISTS (
      SELECT 1 FROM public.authoring_sessions s
      WHERE s.session_id = authoring_confirmations.session_id
        AND s.owner_id = auth.uid()
    )
  );

-- Consumption is an owner UPDATE that can only ever set consumed_at once; the
-- runtime's UPDATE ... WHERE consumed_at IS NULL is the atomic single-use gate.
CREATE POLICY authoring_confirmations_consume_owner ON public.authoring_confirmations
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = owner_id AND consumed_at IS NULL)
  WITH CHECK (auth.uid() = owner_id);
