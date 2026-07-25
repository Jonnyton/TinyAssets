-- 010 - Fixture-only dark paid-request workflow and accounting CAS.
-- FOUNDER-GATED: this prototype migration is not production authority.
--
-- Durable rows own the request/bid/match/claim spine. Notifications are
-- invalidations backed by the outbox. The accounting function records only
-- logical intent and can never authorize wallet funding or a chain effect.

CREATE SCHEMA market_workflow;

DO $roles$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'tinyassets_fixture_workflow_owner'
  ) THEN
    CREATE ROLE tinyassets_fixture_workflow_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'tinyassets_fixture_workflow_command'
  ) THEN
    CREATE ROLE tinyassets_fixture_workflow_command NOLOGIN;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'tinyassets_fixture_workflow_reader'
  ) THEN
    CREATE ROLE tinyassets_fixture_workflow_reader NOLOGIN;
  END IF;
END
$roles$;

CREATE TABLE market_workflow.requests (
  request_id                 uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  tenant_id                  text NOT NULL,
  requester_user_id          uuid NOT NULL REFERENCES public.users(user_id),
  capability_digest          text NOT NULL,
  payload_sha256             text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  budget_micros              bigint NOT NULL CHECK (budget_micros > 0),
  spend_cap_micros           bigint NOT NULL CHECK (
                                spend_cap_micros > 0
                                AND spend_cap_micros <= budget_micros
                              ),
  bid_window_ends_at         timestamptz NOT NULL,
  deadline                   timestamptz NOT NULL CHECK (deadline > bid_window_ends_at),
  acceptance_policy          text NOT NULL,
  settlement_policy_version  text NOT NULL,
  visibility                 text NOT NULL CHECK (
                                visibility IN ('self', 'network', 'paid', 'public')
                              ),
  fanout_limit               smallint NOT NULL CHECK (fanout_limit BETWEEN 1 AND 16),
  state                      text NOT NULL CHECK (
                                state IN (
                                  'pending', 'bidding', 'claimed', 'running',
                                  'completed', 'accepted', 'auto_accepted',
                                  'settled', 'cancelled', 'expired', 'failed',
                                  'refunded', 'disputed'
                                )
                              ),
  version                    bigint NOT NULL CHECK (version > 0),
  idempotency_key            text NOT NULL CHECK (
                                idempotency_key <> ''
                                AND octet_length(idempotency_key) <= 128
                              ),
  command_sha256             text NOT NULL CHECK (
                                command_sha256 ~ '^[0-9a-f]{64}$'
                              ),
  winning_bid_id             uuid,
  winning_bid_version        bigint CHECK (winning_bid_version > 0),
  winning_match_id           uuid,
  settlement_tx_id           bigint REFERENCES market.transactions(tx_id),
  settlement_sha256          text CHECK (
                                settlement_sha256 IS NULL
                                OR settlement_sha256 ~ '^[0-9a-f]{64}$'
                              ),
  real_fund_authorized       boolean NOT NULL DEFAULT false CHECK (
                                real_fund_authorized = false
                              ),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key),
  UNIQUE (tenant_id, request_id)
);

CREATE TABLE market_workflow.bids (
  bid_id                    uuid NOT NULL,
  bid_version               bigint NOT NULL CHECK (bid_version > 0),
  request_id                uuid NOT NULL,
  tenant_id                 text NOT NULL,
  host_id                   uuid NOT NULL,
  host_owner_user_id        uuid NOT NULL REFERENCES public.users(user_id),
  capability_digest         text NOT NULL,
  size_mtok                 integer NOT NULL CHECK (size_mtok IN (1, 10, 100)),
  price_micros_per_mtok     bigint NOT NULL CHECK (price_micros_per_mtok > 0),
  expires_at                timestamptz NOT NULL,
  capacity_grant_id         uuid NOT NULL,
  capacity_fence            bigint NOT NULL CHECK (capacity_fence > 0),
  quote_id                  text,
  quote_version             bigint,
  quote_digest              text,
  state                     text NOT NULL CHECK (
                               state IN (
                                 'offered', 'cancelled', 'expired',
                                 'revoked', 'claimed'
                               )
                             ),
  is_current                boolean NOT NULL DEFAULT true,
  command_sha256            text NOT NULL CHECK (
                               command_sha256 ~ '^[0-9a-f]{64}$'
                             ),
  created_at                timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (bid_id, bid_version),
  FOREIGN KEY (tenant_id, request_id)
    REFERENCES market_workflow.requests(tenant_id, request_id),
  CHECK (
    (quote_id IS NULL AND quote_version IS NULL AND quote_digest IS NULL)
    OR (
      quote_id IS NOT NULL
      AND quote_version > 0
      AND quote_digest ~ '^[0-9a-f]{64}$'
    )
  )
);
CREATE UNIQUE INDEX bids_one_current_version
  ON market_workflow.bids (tenant_id, bid_id)
  WHERE is_current;
CREATE INDEX bids_eligible_snapshot
  ON market_workflow.bids (
    tenant_id, request_id, state, expires_at, bid_id, bid_version
  )
  WHERE is_current;

ALTER TABLE market_workflow.requests
  ADD CONSTRAINT requests_winning_bid_fk
  FOREIGN KEY (winning_bid_id, winning_bid_version)
  REFERENCES market_workflow.bids(bid_id, bid_version)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE market_workflow.matches (
  match_id                  uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  tenant_id                 text NOT NULL,
  request_id                uuid NOT NULL,
  request_version           bigint NOT NULL CHECK (request_version > 0),
  matcher_version           text NOT NULL,
  need_mtok                 integer NOT NULL CHECK (need_mtok > 0),
  total_cost_micros         bigint NOT NULL CHECK (total_cost_micros > 0),
  decision_sha256           text NOT NULL CHECK (
                               decision_sha256 ~ '^[0-9a-f]{64}$'
                             ),
  rejected_bids             jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                               jsonb_typeof(rejected_bids) = 'array'
                             ),
  created_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, match_id),
  FOREIGN KEY (tenant_id, request_id)
    REFERENCES market_workflow.requests(tenant_id, request_id)
);

CREATE TABLE market_workflow.match_bids (
  tenant_id                 text NOT NULL,
  match_id                  uuid NOT NULL,
  bid_id                    uuid NOT NULL,
  bid_version               bigint NOT NULL CHECK (bid_version > 0),
  slot_index                smallint NOT NULL CHECK (slot_index BETWEEN 0 AND 15),
  PRIMARY KEY (tenant_id, match_id, bid_id),
  UNIQUE (tenant_id, match_id, slot_index),
  FOREIGN KEY (tenant_id, match_id)
    REFERENCES market_workflow.matches(tenant_id, match_id),
  FOREIGN KEY (bid_id, bid_version)
    REFERENCES market_workflow.bids(bid_id, bid_version)
);

ALTER TABLE market_workflow.requests
  ADD CONSTRAINT requests_winning_match_fk
  FOREIGN KEY (tenant_id, winning_match_id)
  REFERENCES market_workflow.matches(tenant_id, match_id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE market_workflow.fanout_slots (
  slot_id                   uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  tenant_id                 text NOT NULL,
  request_id                uuid NOT NULL,
  match_id                  uuid NOT NULL,
  slot_index                smallint NOT NULL CHECK (slot_index BETWEEN 0 AND 15),
  bid_id                    uuid NOT NULL,
  bid_version               bigint NOT NULL CHECK (bid_version > 0),
  state                     text NOT NULL CHECK (state IN ('open', 'claimed')),
  version                   bigint NOT NULL CHECK (version > 0),
  UNIQUE (tenant_id, request_id, slot_index),
  FOREIGN KEY (tenant_id, request_id)
    REFERENCES market_workflow.requests(tenant_id, request_id),
  FOREIGN KEY (tenant_id, match_id)
    REFERENCES market_workflow.matches(tenant_id, match_id),
  FOREIGN KEY (bid_id, bid_version)
    REFERENCES market_workflow.bids(bid_id, bid_version)
);

CREATE TABLE market_workflow.claims (
  claim_id                  uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  tenant_id                 text NOT NULL,
  request_id                uuid NOT NULL,
  request_version           bigint NOT NULL CHECK (request_version > 0),
  match_id                  uuid NOT NULL,
  actor_id                  uuid NOT NULL REFERENCES public.users(user_id),
  command_sha256            text NOT NULL CHECK (
                               command_sha256 ~ '^[0-9a-f]{64}$'
                             ),
  created_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, request_id),
  FOREIGN KEY (tenant_id, request_id)
    REFERENCES market_workflow.requests(tenant_id, request_id),
  FOREIGN KEY (tenant_id, match_id)
    REFERENCES market_workflow.matches(tenant_id, match_id)
);

CREATE TABLE market_workflow.transition_events (
  event_id                  bigserial PRIMARY KEY,
  tenant_id                 text NOT NULL,
  request_id                uuid NOT NULL,
  prior_state               text,
  new_state                 text NOT NULL,
  request_version           bigint NOT NULL CHECK (request_version > 0),
  actor_id                  uuid NOT NULL REFERENCES public.users(user_id),
  grant_id                  uuid,
  command_sha256            text NOT NULL CHECK (
                               command_sha256 ~ '^[0-9a-f]{64}$'
                             ),
  related_ids               jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
                               jsonb_typeof(related_ids) = 'array'
                             ),
  created_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, request_id, request_version),
  FOREIGN KEY (tenant_id, request_id)
    REFERENCES market_workflow.requests(tenant_id, request_id)
);

CREATE TABLE market_workflow.outbox (
  shard_cursor              bigserial PRIMARY KEY,
  event_id                  bigint NOT NULL UNIQUE
                               REFERENCES market_workflow.transition_events(event_id),
  tenant_id                 text NOT NULL,
  capability_digest         text NOT NULL,
  request_id                uuid NOT NULL,
  request_version           bigint NOT NULL CHECK (request_version > 0),
  visibility                text NOT NULL,
  fanout_limit              smallint NOT NULL CHECK (fanout_limit BETWEEN 1 AND 16),
  bid_window_ends_at        timestamptz NOT NULL,
  deadline                  timestamptz NOT NULL,
  created_at                timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, request_id)
    REFERENCES market_workflow.requests(tenant_id, request_id)
);
CREATE INDEX outbox_shard_cursor
  ON market_workflow.outbox (
    tenant_id, capability_digest, shard_cursor
  );

CREATE TABLE market_workflow.authority_grants (
  grant_id                  uuid PRIMARY KEY,
  tenant_id                 text NOT NULL,
  host_actor_id             uuid NOT NULL REFERENCES public.users(user_id),
  target_actor_id           uuid NOT NULL REFERENCES public.users(user_id),
  account                   text NOT NULL CHECK (
                              account ~ '^escrow:[^\s]+$'
                            ),
  allowed_actions           text[] NOT NULL,
  max_amount_micros         bigint NOT NULL CHECK (max_amount_micros > 0),
  issued_at                 timestamptz NOT NULL,
  expires_at                timestamptz NOT NULL CHECK (expires_at > issued_at),
  revocation_generation     bigint NOT NULL CHECK (revocation_generation >= 0),
  revoked                   boolean NOT NULL DEFAULT false,
  signature_sha256          text NOT NULL CHECK (
                               signature_sha256 ~ '^[0-9a-f]{64}$'
                             )
);

CREATE TABLE market_workflow.command_log (
  tenant_id                 text NOT NULL,
  idempotency_key           text NOT NULL CHECK (
                               idempotency_key <> ''
                               AND octet_length(idempotency_key) <= 128
                             ),
  command_sha256            text NOT NULL CHECK (
                               command_sha256 ~ '^[0-9a-f]{64}$'
                             ),
  request_id                uuid,
  result_version            bigint,
  result_state              text,
  created_at                timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE FUNCTION market_workflow.submit_request(
  p_canonical_body bytea,
  p_supplied_sha256 text
) RETURNS TABLE(status text, request_id uuid, version bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, market_workflow, auth, pg_temp
AS $function$
DECLARE
  v_body                    jsonb;
  v_sha256                  text;
  v_tenant_id               text;
  v_subject_id              uuid;
  v_requester_user_id       uuid;
  v_idempotency_key         text;
  v_request_id              uuid;
  v_existing_sha256         text;
  v_existing_version        bigint;
  v_inserted                integer;
  v_event_id                bigint;
BEGIN
  IF p_canonical_body IS NULL OR octet_length(p_canonical_body) > 16384 THEN
    RAISE EXCEPTION 'canonical request body is required and bounded';
  END IF;
  v_sha256 := encode(pg_catalog.sha256(p_canonical_body), 'hex');
  IF p_supplied_sha256 IS NULL OR p_supplied_sha256 <> v_sha256 THEN
    RAISE EXCEPTION 'canonical hash mismatch';
  END IF;
  BEGIN
    v_body := convert_from(p_canonical_body, 'UTF8')::jsonb;
    v_subject_id := auth.uid();
    v_tenant_id := nullif(current_setting('app.tenant_id', true), '');
    v_requester_user_id := (v_body->>'requester_user_id')::uuid;
  EXCEPTION
    WHEN OTHERS THEN
      RAISE EXCEPTION 'invalid canonical request body';
  END;
  v_idempotency_key := v_body->>'idempotency_key';
  IF v_body->>'schema_version' IS DISTINCT FROM '1'
     OR v_subject_id IS NULL
     OR v_tenant_id IS NULL
     OR v_requester_user_id IS DISTINCT FROM v_subject_id
     OR (
       v_body->>'tenant_advisory' IS NOT NULL
       AND v_body->>'tenant_advisory' IS DISTINCT FROM v_tenant_id
     )
     OR v_idempotency_key IS NULL
     OR v_idempotency_key = ''
     OR octet_length(v_idempotency_key) > 128
     OR v_body->>'payload_sha256' !~ '^[0-9a-f]{64}$'
     OR (v_body->>'budget_micros') !~ '^[1-9][0-9]*$'
     OR (v_body->>'spend_cap_micros') !~ '^[1-9][0-9]*$'
     OR (v_body->>'fanout_limit') !~ '^[1-9][0-9]*$' THEN
    RAISE EXCEPTION 'verified requester authority and bounded fields are required';
  END IF;

  INSERT INTO market_workflow.command_log (
    tenant_id, idempotency_key, command_sha256
  ) VALUES (
    v_tenant_id, v_idempotency_key, v_sha256
  )
  ON CONFLICT (tenant_id, idempotency_key) DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  IF v_inserted = 0 THEN
    SELECT log.command_sha256, log.request_id, log.result_version
      INTO v_existing_sha256, v_request_id, v_existing_version
      FROM market_workflow.command_log AS log
     WHERE log.tenant_id = v_tenant_id
       AND log.idempotency_key = v_idempotency_key
     FOR UPDATE;
    IF v_existing_sha256 IS DISTINCT FROM v_sha256 THEN
      RAISE EXCEPTION 'idempotency conflict';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, v_request_id, v_existing_version;
    RETURN;
  END IF;

  IF (v_body->>'spend_cap_micros')::bigint >
     (v_body->>'budget_micros')::bigint
     OR (v_body->>'fanout_limit')::integer NOT BETWEEN 1 AND 16
     OR (v_body->>'deadline')::bigint <=
        (v_body->>'bid_window_ends_at')::bigint
     OR v_body->>'visibility' NOT IN ('self', 'network', 'paid', 'public') THEN
    RAISE EXCEPTION 'request bounds are invalid';
  END IF;

  v_request_id := pg_catalog.gen_random_uuid();
  INSERT INTO market_workflow.requests (
    request_id, tenant_id, requester_user_id, capability_digest,
    payload_sha256, budget_micros, spend_cap_micros, bid_window_ends_at,
    deadline, acceptance_policy, settlement_policy_version, visibility,
    fanout_limit, state, version, idempotency_key, command_sha256
  ) VALUES (
    v_request_id,
    v_tenant_id,
    v_requester_user_id,
    v_body->>'capability_digest',
    v_body->>'payload_sha256',
    (v_body->>'budget_micros')::bigint,
    (v_body->>'spend_cap_micros')::bigint,
    to_timestamp((v_body->>'bid_window_ends_at')::bigint),
    to_timestamp((v_body->>'deadline')::bigint),
    v_body->>'acceptance_policy',
    v_body->>'settlement_policy_version',
    v_body->>'visibility',
    (v_body->>'fanout_limit')::smallint,
    'pending',
    1,
    v_idempotency_key,
    v_sha256
  );
  INSERT INTO market_workflow.transition_events (
    tenant_id, request_id, prior_state, new_state, request_version,
    actor_id, command_sha256
  ) VALUES (
    v_tenant_id, v_request_id, NULL, 'pending', 1,
    v_subject_id, v_sha256
  ) RETURNING event_id INTO v_event_id;
  UPDATE market_workflow.command_log
     SET request_id = v_request_id, result_version = 1, result_state = 'pending'
   WHERE tenant_id = v_tenant_id
     AND idempotency_key = v_idempotency_key;
  RETURN QUERY SELECT 'applied'::text, v_request_id, 1::bigint;
END
$function$;

CREATE FUNCTION market_workflow.transition_request(
  p_canonical_body bytea,
  p_supplied_sha256 text
) RETURNS TABLE(status text, request_id uuid, state text, version bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, market_workflow, auth, pg_temp
AS $function$
DECLARE
  v_body                    jsonb;
  v_sha256                  text;
  v_tenant_id               text;
  v_subject_id              uuid;
  v_request_id              uuid;
  v_idempotency_key         text;
  v_expected_version        bigint;
  v_action                  text;
  v_request                 market_workflow.requests%ROWTYPE;
  v_target_state            text;
  v_existing_sha256         text;
  v_existing_version        bigint;
  v_existing_state          text;
  v_inserted                integer;
  v_event_id                bigint;
BEGIN
  IF p_canonical_body IS NULL OR octet_length(p_canonical_body) > 4096 THEN
    RAISE EXCEPTION 'canonical transition body is required and bounded';
  END IF;
  v_sha256 := encode(pg_catalog.sha256(p_canonical_body), 'hex');
  IF p_supplied_sha256 IS NULL OR p_supplied_sha256 <> v_sha256 THEN
    RAISE EXCEPTION 'canonical hash mismatch';
  END IF;
  BEGIN
    v_body := convert_from(p_canonical_body, 'UTF8')::jsonb;
    v_subject_id := auth.uid();
    v_tenant_id := nullif(current_setting('app.tenant_id', true), '');
    v_request_id := (v_body->>'request_id')::uuid;
    v_expected_version := (v_body->>'expected_version')::bigint;
  EXCEPTION
    WHEN OTHERS THEN
      RAISE EXCEPTION 'invalid canonical transition body';
  END;
  v_idempotency_key := v_body->>'idempotency_key';
  v_action := v_body->>'action';
  IF v_body->>'schema_version' IS DISTINCT FROM '1'
     OR v_subject_id IS NULL OR v_tenant_id IS NULL
     OR v_idempotency_key IS NULL OR v_idempotency_key = ''
     OR octet_length(v_idempotency_key) > 128 THEN
    RAISE EXCEPTION 'verified transition authority is required';
  END IF;

  INSERT INTO market_workflow.command_log (
    tenant_id, idempotency_key, command_sha256, request_id
  ) VALUES (
    v_tenant_id, v_idempotency_key, v_sha256, v_request_id
  )
  ON CONFLICT (tenant_id, idempotency_key) DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  IF v_inserted = 0 THEN
    SELECT log.command_sha256, log.result_version, log.result_state
      INTO v_existing_sha256, v_existing_version, v_existing_state
      FROM market_workflow.command_log AS log
     WHERE log.tenant_id = v_tenant_id
       AND log.idempotency_key = v_idempotency_key
     FOR UPDATE;
    IF v_existing_sha256 IS DISTINCT FROM v_sha256 THEN
      RAISE EXCEPTION 'idempotency conflict';
    END IF;
    RETURN QUERY
      SELECT 'replayed'::text, v_request_id, v_existing_state, v_existing_version;
    RETURN;
  END IF;

  SELECT req.*
    INTO v_request
    FROM market_workflow.requests AS req
   WHERE req.tenant_id = v_tenant_id
     AND req.request_id = v_request_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'request not found';
  END IF;
  IF v_request.requester_user_id IS DISTINCT FROM v_subject_id THEN
    RAISE EXCEPTION 'requester authority is required';
  END IF;
  IF v_request.version <> v_expected_version THEN
    RAISE EXCEPTION 'request version contention';
  END IF;
  IF v_action = 'open_bidding' AND v_request.state = 'pending' THEN
    v_target_state := 'bidding';
  ELSIF v_action = 'cancel_request'
        AND v_request.state IN ('pending', 'bidding') THEN
    v_target_state := 'cancelled';
  ELSE
    RAISE EXCEPTION 'state transition is forbidden';
  END IF;

  UPDATE market_workflow.requests AS target
     SET state = v_target_state,
         version = target.version + 1,
         updated_at = now()
   WHERE target.tenant_id = v_tenant_id
     AND target.request_id = v_request_id;
  INSERT INTO market_workflow.transition_events (
    tenant_id, request_id, prior_state, new_state, request_version,
    actor_id, command_sha256
  ) VALUES (
    v_tenant_id, v_request_id, v_request.state, v_target_state,
    v_request.version + 1, v_subject_id, v_sha256
  ) RETURNING event_id INTO v_event_id;
  INSERT INTO market_workflow.outbox (
    event_id, tenant_id, capability_digest, request_id, request_version,
    visibility, fanout_limit, bid_window_ends_at, deadline
  ) VALUES (
    v_event_id, v_tenant_id, v_request.capability_digest, v_request_id,
    v_request.version + 1, v_request.visibility, v_request.fanout_limit,
    v_request.bid_window_ends_at, v_request.deadline
  );
  UPDATE market_workflow.command_log
     SET result_version = v_request.version + 1,
         result_state = v_target_state
   WHERE tenant_id = v_tenant_id
     AND idempotency_key = v_idempotency_key;
  RETURN QUERY
    SELECT 'applied'::text, v_request_id, v_target_state, v_request.version + 1;
END
$function$;

CREATE FUNCTION market_workflow.apply_accounting_settlement(
  p_request_id uuid,
  p_expected_version bigint,
  p_canonical_body bytea,
  p_supplied_sha256 text
) RETURNS TABLE(status text, tx_id bigint, version bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, market_workflow, market, auth, pg_temp
AS $function$
DECLARE
  v_body                    jsonb;
  v_sha256                  text;
  v_tenant_id               text;
  v_subject_id              uuid;
  v_request                 market_workflow.requests%ROWTYPE;
  v_bid                     market_workflow.bids%ROWTYPE;
  v_match                   market_workflow.matches%ROWTYPE;
  v_tx_status               text;
  v_tx_id                   bigint;
  v_grant_id                uuid;
  v_amount_micros           bigint;
  v_event_id                bigint;
BEGIN
  IF p_canonical_body IS NULL OR octet_length(p_canonical_body) > 16384 THEN
    RAISE EXCEPTION 'canonical settlement body is required and bounded';
  END IF;
  v_sha256 := encode(pg_catalog.sha256(p_canonical_body), 'hex');
  IF p_supplied_sha256 IS NULL OR p_supplied_sha256 <> v_sha256 THEN
    RAISE EXCEPTION 'canonical hash mismatch';
  END IF;
  BEGIN
    v_body := convert_from(p_canonical_body, 'UTF8')::jsonb;
    v_subject_id := auth.uid();
    v_tenant_id := nullif(current_setting('app.tenant_id', true), '');
    v_amount_micros := (v_body->>'amount_micros')::bigint;
  EXCEPTION
    WHEN OTHERS THEN
      RAISE EXCEPTION 'invalid canonical settlement body';
  END;
  IF v_subject_id IS NULL OR v_tenant_id IS NULL
     OR v_body->'authority'->>'subject_id' IS DISTINCT FROM v_subject_id::text
     OR v_body->'authority'->>'tenant_id' IS DISTINCT FROM v_tenant_id
     OR v_body->>'business_reference' IS DISTINCT FROM p_request_id::text
     OR v_body->>'expected_state_version' IS DISTINCT FROM p_expected_version::text
     OR v_body->>'escrow_account' IS DISTINCT FROM 'escrow:' || p_request_id::text THEN
    RAISE EXCEPTION 'verified settlement authority or business binding mismatch';
  END IF;

  SELECT req.*
    INTO v_request
    FROM market_workflow.requests AS req
   WHERE req.tenant_id = v_tenant_id
     AND req.request_id = p_request_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'request not found';
  END IF;
  IF v_request.state = 'settled' THEN
    IF v_request.settlement_sha256 IS DISTINCT FROM v_sha256 THEN
      RAISE EXCEPTION 'idempotency conflict';
    END IF;
    RETURN QUERY
      SELECT 'replayed'::text, v_request.settlement_tx_id, v_request.version;
    RETURN;
  END IF;
  IF v_request.state NOT IN ('accepted', 'auto_accepted')
     OR v_request.version <> p_expected_version
     OR v_request.requester_user_id::text IS DISTINCT FROM
        v_body->'authority'->>'requester_user_id'
     OR v_request.winning_bid_id IS NULL
     OR v_request.winning_match_id IS NULL THEN
    RAISE EXCEPTION 'business state, version, or requester authority mismatch';
  END IF;

  SELECT bid.*
    INTO v_bid
    FROM market_workflow.bids AS bid
   WHERE bid.tenant_id = v_tenant_id
     AND bid.bid_id = v_request.winning_bid_id
     AND bid.bid_version = v_request.winning_bid_version
     AND bid.state = 'claimed'
   FOR UPDATE;
  IF NOT FOUND
     OR v_bid.host_owner_user_id::text IS DISTINCT FROM
        v_body->'authority'->>'host_owner_user_id' THEN
    RAISE EXCEPTION 'winning bid authority mismatch';
  END IF;

  SELECT decision.*
    INTO v_match
    FROM market_workflow.matches AS decision
   WHERE decision.tenant_id = v_tenant_id
     AND decision.match_id = v_request.winning_match_id
     AND decision.request_id = p_request_id
   FOR UPDATE;
  IF NOT FOUND OR NOT EXISTS (
    SELECT 1
      FROM market_workflow.match_bids AS selected
     WHERE selected.tenant_id = v_tenant_id
       AND selected.match_id = v_request.winning_match_id
       AND selected.bid_id = v_request.winning_bid_id
       AND selected.bid_version = v_request.winning_bid_version
  ) THEN
    RAISE EXCEPTION 'winning match and bid binding mismatch';
  END IF;
  IF v_amount_micros IS DISTINCT FROM v_match.total_cost_micros
     OR v_amount_micros > v_request.spend_cap_micros THEN
    RAISE EXCEPTION 'settlement amount mismatch';
  END IF;

  IF v_subject_id <> v_request.requester_user_id THEN
    BEGIN
      v_grant_id := (v_body->'authority'->'grant'->>'grant_id')::uuid;
    EXCEPTION
      WHEN OTHERS THEN
        RAISE EXCEPTION 'bounded on-behalf grant is required';
    END;
    PERFORM 1
      FROM market_workflow.authority_grants AS authority_grant
     WHERE authority_grant.grant_id = v_grant_id
       AND authority_grant.tenant_id = v_tenant_id
       AND authority_grant.host_actor_id = v_subject_id
       AND authority_grant.target_actor_id = v_request.requester_user_id
       AND authority_grant.account = 'escrow:' || p_request_id::text
       AND 'settle' = ANY(authority_grant.allowed_actions)
       AND authority_grant.max_amount_micros >= v_amount_micros
       AND authority_grant.issued_at <= now()
       AND authority_grant.expires_at > now()
       AND NOT authority_grant.revoked
       AND authority_grant.revocation_generation::text IS NOT DISTINCT FROM
           v_body->'authority'->'grant'->>'revocation_generation'
       AND authority_grant.signature_sha256 IS NOT DISTINCT FROM
           v_body->'authority'->'grant'->>'verified_signature_sha256'
     FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'bounded on-behalf grant is required';
    END IF;
  END IF;

  SELECT applied.status, applied.tx_id
    INTO v_tx_status, v_tx_id
    FROM market.apply_settlement(p_canonical_body, v_sha256) AS applied;
  PERFORM market.assert_drained('escrow:' || p_request_id::text);
  UPDATE market_workflow.requests AS target
     SET state = 'settled',
         version = target.version + 1,
         settlement_tx_id = v_tx_id,
         settlement_sha256 = v_sha256,
         updated_at = now()
   WHERE target.tenant_id = v_tenant_id
     AND target.request_id = p_request_id;
  INSERT INTO market_workflow.transition_events (
    tenant_id, request_id, prior_state, new_state, request_version,
    actor_id, grant_id, command_sha256, related_ids
  ) VALUES (
    v_tenant_id, p_request_id, v_request.state, 'settled',
    v_request.version + 1, v_subject_id, v_grant_id, v_sha256,
    jsonb_build_array(v_request.winning_bid_id, v_tx_id)
  ) RETURNING event_id INTO v_event_id;
  RETURN QUERY
    SELECT v_tx_status, v_tx_id, v_request.version + 1;
END
$function$;

CREATE FUNCTION market_workflow.workflow_status()
RETURNS TABLE(status text, pending_count bigint, settlement_available boolean)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, market_workflow, auth, pg_temp
AS $function$
DECLARE
  v_tenant_id text;
  v_subject_id uuid;
BEGIN
  v_subject_id := auth.uid();
  v_tenant_id := nullif(current_setting('app.tenant_id', true), '');
  IF v_subject_id IS NULL OR v_tenant_id IS NULL THEN
    RAISE EXCEPTION 'verified read authority is required';
  END IF;
  RETURN QUERY
    SELECT
      'dark_pending'::text,
      count(*)::bigint,
      false
    FROM market_workflow.requests AS req
    WHERE req.tenant_id = v_tenant_id
      AND req.requester_user_id = v_subject_id
      AND req.state IN ('pending', 'bidding', 'claimed', 'running');
END
$function$;

CREATE FUNCTION market_workflow.can_read_request(
  p_tenant_id text,
  p_request_id uuid
) RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, market_workflow, auth, pg_temp
AS $function$
  SELECT
    p_tenant_id = nullif(current_setting('app.tenant_id', true), '')
    AND EXISTS (
      SELECT 1
        FROM market_workflow.requests AS request
       WHERE request.tenant_id = p_tenant_id
         AND request.request_id = p_request_id
         AND (
           request.requester_user_id = auth.uid()
           OR EXISTS (
             SELECT 1
               FROM market_workflow.matches AS decision
               JOIN market_workflow.match_bids AS selected
                 ON selected.tenant_id = decision.tenant_id
                AND selected.match_id = decision.match_id
               JOIN market_workflow.bids AS bid
                 ON bid.bid_id = selected.bid_id
                AND bid.bid_version = selected.bid_version
              WHERE decision.tenant_id = p_tenant_id
                AND decision.request_id = p_request_id
                AND bid.host_owner_user_id = auth.uid()
           )
         )
    )
$function$;

ALTER SCHEMA market_workflow OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.requests OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.bids OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.matches OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.match_bids OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.fanout_slots OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.claims OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.transition_events OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.outbox OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.authority_grants OWNER TO tinyassets_fixture_workflow_owner;
ALTER TABLE market_workflow.command_log OWNER TO tinyassets_fixture_workflow_owner;
ALTER SEQUENCE market_workflow.transition_events_event_id_seq
  OWNER TO tinyassets_fixture_workflow_owner;
ALTER SEQUENCE market_workflow.outbox_shard_cursor_seq
  OWNER TO tinyassets_fixture_workflow_owner;
ALTER FUNCTION market_workflow.submit_request(bytea, text)
  OWNER TO tinyassets_fixture_workflow_owner;
ALTER FUNCTION market_workflow.transition_request(bytea, text)
  OWNER TO tinyassets_fixture_workflow_owner;
ALTER FUNCTION market_workflow.apply_accounting_settlement(uuid, bigint, bytea, text)
  OWNER TO tinyassets_fixture_workflow_owner;
ALTER FUNCTION market_workflow.workflow_status()
  OWNER TO tinyassets_fixture_workflow_owner;
ALTER FUNCTION market_workflow.can_read_request(text, uuid)
  OWNER TO tinyassets_fixture_workflow_owner;

ALTER TABLE market_workflow.requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.bids ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.match_bids ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.fanout_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.transition_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_workflow.outbox ENABLE ROW LEVEL SECURITY;

CREATE POLICY workflow_requests_read ON market_workflow.requests
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (market_workflow.can_read_request(tenant_id, request_id));
CREATE POLICY workflow_bids_read ON market_workflow.bids
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')
    AND (
      host_owner_user_id = auth.uid()
      OR market_workflow.can_read_request(tenant_id, request_id)
    )
  );
CREATE POLICY workflow_matches_read ON market_workflow.matches
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (market_workflow.can_read_request(tenant_id, request_id));
CREATE POLICY workflow_match_bids_read ON market_workflow.match_bids
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (
    EXISTS (
      SELECT 1
        FROM market_workflow.matches AS decision
       WHERE decision.tenant_id = match_bids.tenant_id
         AND decision.match_id = match_bids.match_id
         AND market_workflow.can_read_request(
               decision.tenant_id, decision.request_id
             )
    )
  );
CREATE POLICY workflow_slots_read ON market_workflow.fanout_slots
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (market_workflow.can_read_request(tenant_id, request_id));
CREATE POLICY workflow_claims_read ON market_workflow.claims
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (market_workflow.can_read_request(tenant_id, request_id));
CREATE POLICY workflow_events_read ON market_workflow.transition_events
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (market_workflow.can_read_request(tenant_id, request_id));
CREATE POLICY workflow_outbox_read ON market_workflow.outbox
  FOR SELECT TO tinyassets_fixture_workflow_reader
  USING (market_workflow.can_read_request(tenant_id, request_id));

REVOKE ALL ON SCHEMA market_workflow FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA market_workflow FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA market_workflow FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA market_workflow FROM PUBLIC;
REVOKE ALL ON SCHEMA market_workflow FROM tinyassets_fixture_app;
REVOKE ALL ON ALL TABLES IN SCHEMA market_workflow FROM tinyassets_fixture_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA market_workflow FROM tinyassets_fixture_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA market_workflow FROM tinyassets_fixture_app;

GRANT USAGE ON SCHEMA market_workflow
  TO tinyassets_fixture_workflow_command,
     tinyassets_fixture_workflow_reader,
     tinyassets_fixture_settlement;
GRANT EXECUTE ON FUNCTION market_workflow.submit_request(bytea, text)
  TO tinyassets_fixture_workflow_command;
GRANT EXECUTE ON FUNCTION market_workflow.transition_request(bytea, text)
  TO tinyassets_fixture_workflow_command;
GRANT EXECUTE ON FUNCTION market_workflow.apply_accounting_settlement(
  uuid, bigint, bytea, text
) TO tinyassets_fixture_settlement;
GRANT EXECUTE ON FUNCTION market_workflow.workflow_status()
  TO tinyassets_fixture_workflow_reader;
GRANT EXECUTE ON FUNCTION market_workflow.can_read_request(text, uuid)
  TO tinyassets_fixture_workflow_reader;
GRANT SELECT ON
  market_workflow.requests,
  market_workflow.bids,
  market_workflow.matches,
  market_workflow.match_bids,
  market_workflow.fanout_slots,
  market_workflow.claims,
  market_workflow.transition_events,
  market_workflow.outbox
TO tinyassets_fixture_workflow_reader;

REVOKE EXECUTE ON FUNCTION market.apply_settlement(bytea, text)
  FROM tinyassets_fixture_settlement;
GRANT USAGE ON SCHEMA market TO tinyassets_fixture_workflow_owner;
GRANT EXECUTE ON FUNCTION market.apply_settlement(bytea, text)
  TO tinyassets_fixture_workflow_owner;
GRANT EXECUTE ON FUNCTION market.assert_drained(text)
  TO tinyassets_fixture_workflow_owner;
GRANT USAGE ON SCHEMA auth
  TO tinyassets_fixture_workflow_owner;
GRANT EXECUTE ON FUNCTION auth.uid()
  TO tinyassets_fixture_workflow_owner;
