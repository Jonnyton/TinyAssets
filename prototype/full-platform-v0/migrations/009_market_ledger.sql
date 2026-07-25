-- 009 — Fixture-only double-entry market ledger and its one bounded transport.
-- FOUNDER-GATED: do not apply this prototype chain to live data.
--
-- public.ledger remains frozen v1 history.  The market schema is logical
-- accounting only: a committed row proves neither wallet funding nor a chain
-- settlement.  No user-facing role can write it, and all accepted settlements
-- pass through apply_settlement(bytea,text).

CREATE SCHEMA IF NOT EXISTS market;

DO $roles$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'tinyassets_fixture_market_owner'
  ) THEN
    CREATE ROLE tinyassets_fixture_market_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'tinyassets_fixture_settlement'
  ) THEN
    CREATE ROLE tinyassets_fixture_settlement NOLOGIN;
  END IF;
END
$roles$;

CREATE TABLE market.transactions (
  tx_id            bigserial PRIMARY KEY,
  tenant_id        text NOT NULL,
  idempotency_key  text NOT NULL,
  request_sha256   text NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  encoding_version smallint NOT NULL DEFAULT 1 CHECK (encoding_version = 1),
  memo             text NOT NULL DEFAULT '',
  at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE market.postings (
  posting_id   bigserial PRIMARY KEY,
  tx_id        bigint NOT NULL REFERENCES market.transactions(tx_id),
  account      text NOT NULL,
  delta_micros bigint NOT NULL,
  CONSTRAINT postings_account_shape CHECK (
    account = 'treasury'
    OR account ~ '^(user|escrow|collateral):[^\s]+$'
  )
);
CREATE INDEX postings_account ON market.postings (account, tx_id);
CREATE INDEX postings_tx ON market.postings (tx_id);

CREATE TABLE market.balances (
  account        text PRIMARY KEY,
  balance_micros bigint NOT NULL DEFAULT 0 CHECK (balance_micros >= 0)
);

-- Private primitive.  It consumes only values already checked and derived by
-- apply_settlement.  No service/application role receives EXECUTE.
CREATE FUNCTION market.apply_tx(
  p_tenant_id       text,
  p_idempotency_key text,
  p_request_sha256  text,
  p_memo            text,
  p_postings        jsonb
) RETURNS TABLE(status text, tx_id bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, market, pg_temp
AS $function$
DECLARE
  v_tx_id bigint;
  v_existing_sha256 text;
  v_sum numeric;
  v_rec record;
BEGIN
  INSERT INTO market.transactions (
    tenant_id, idempotency_key, request_sha256, memo
  ) VALUES (
    p_tenant_id, p_idempotency_key, p_request_sha256, p_memo
  )
  ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
  RETURNING market.transactions.tx_id INTO v_tx_id;

  IF v_tx_id IS NULL THEN
    SELECT t.tx_id, t.request_sha256
      INTO v_tx_id, v_existing_sha256
      FROM market.transactions AS t
     WHERE t.tenant_id = p_tenant_id
       AND t.idempotency_key = p_idempotency_key
     FOR SHARE;
    IF v_tx_id IS NULL THEN
      RAISE EXCEPTION 'idempotency contention: existing row is not visible';
    END IF;
    IF v_existing_sha256 <> p_request_sha256 THEN
      RAISE EXCEPTION 'idempotency conflict';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, v_tx_id;
    RETURN;
  END IF;

  SELECT sum((entry->>'delta_micros')::bigint)
    INTO v_sum
    FROM jsonb_array_elements(p_postings) AS entry;
  IF v_sum IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'postings do not zero-sum (sum=%)', v_sum;
  END IF;

  INSERT INTO market.balances (account, balance_micros)
    SELECT entry->>'account', 0
      FROM jsonb_array_elements(p_postings) AS entry
     GROUP BY entry->>'account'
  ON CONFLICT (account) DO NOTHING;

  FOR v_rec IN
    SELECT b.account, b.balance_micros, net.delta
      FROM market.balances AS b
      JOIN (
        SELECT entry->>'account' AS account,
               sum((entry->>'delta_micros')::bigint) AS delta
          FROM jsonb_array_elements(p_postings) AS entry
         GROUP BY entry->>'account'
      ) AS net USING (account)
     ORDER BY b.account
     FOR UPDATE OF b
  LOOP
    IF v_rec.balance_micros + v_rec.delta IS NULL
       OR v_rec.balance_micros + v_rec.delta < 0 THEN
      RAISE EXCEPTION 'overdraft on % (balance %, delta %)',
        v_rec.account, v_rec.balance_micros, v_rec.delta;
    END IF;
  END LOOP;

  UPDATE market.balances AS b
     SET balance_micros = b.balance_micros + net.delta
    FROM (
      SELECT entry->>'account' AS account,
             sum((entry->>'delta_micros')::bigint) AS delta
        FROM jsonb_array_elements(p_postings) AS entry
       GROUP BY entry->>'account'
    ) AS net
   WHERE b.account = net.account;

  INSERT INTO market.postings (tx_id, account, delta_micros)
    SELECT v_tx_id, entry->>'account', (entry->>'delta_micros')::bigint
      FROM jsonb_array_elements(p_postings) AS entry;

  RETURN QUERY SELECT 'applied'::text, v_tx_id;
END
$function$;

-- The only callable logical-accounting transport.  The hash is recomputed
-- from the exact canonical bytes; the body itself supplies all applied fields,
-- so a parallel caller-selected posting/hash representation cannot diverge.
CREATE FUNCTION market.apply_settlement(
  p_canonical_body bytea,
  p_supplied_sha256 text
) RETURNS TABLE(status text, tx_id bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, market, pg_temp
AS $function$
DECLARE
  v_body jsonb;
  v_sha256 text;
  v_tenant_id text;
  v_idempotency_key text;
  v_memo text;
  v_postings jsonb;
  v_action text;
  v_business_reference text;
  v_escrow_account text;
  v_host_owner_user_id text;
  v_expected_state_version bigint;
  v_amount_micros bigint;
  v_escrow_delta bigint;
  v_seller_delta bigint;
  v_bad_account boolean;
  v_fee bigint;
BEGIN
  IF p_canonical_body IS NULL OR octet_length(p_canonical_body) > 16384 THEN
    RAISE EXCEPTION 'canonical body must be at most 16384 bytes';
  END IF;
  v_sha256 := encode(sha256(p_canonical_body), 'hex');
  IF p_supplied_sha256 IS NULL
     OR p_supplied_sha256 !~ '^[0-9a-f]{64}$'
     OR p_supplied_sha256 <> v_sha256 THEN
    RAISE EXCEPTION 'canonical hash mismatch';
  END IF;

  BEGIN
    v_body := convert_from(p_canonical_body, 'UTF8')::jsonb;
  EXCEPTION
    WHEN OTHERS THEN
      RAISE EXCEPTION 'canonical body is not valid UTF-8 JSON';
  END;
  IF jsonb_typeof(v_body) <> 'object'
     OR v_body->>'schema_version' IS DISTINCT FROM '1' THEN
    RAISE EXCEPTION 'unsupported canonical body';
  END IF;

  v_tenant_id := v_body->'authority'->>'tenant_id';
  v_idempotency_key := v_body->>'idempotency_key';
  v_memo := coalesce(v_body->>'memo', '');
  v_postings := v_body->'postings';
  v_action := v_body->>'action';
  v_business_reference := v_body->>'business_reference';
  v_escrow_account := v_body->>'escrow_account';
  v_host_owner_user_id := v_body->'authority'->>'host_owner_user_id';
  IF v_tenant_id IS NULL OR v_tenant_id = ''
     OR octet_length(v_tenant_id) > 128 THEN
    RAISE EXCEPTION 'tenant_id is required and bounded';
  END IF;
  IF v_idempotency_key IS NULL OR v_idempotency_key = ''
     OR octet_length(v_idempotency_key) > 128 THEN
    RAISE EXCEPTION 'idempotency_key is required and bounded';
  END IF;
  IF octet_length(v_memo) > 512 THEN
    RAISE EXCEPTION 'memo exceeds 512 bytes';
  END IF;
  IF v_action IS DISTINCT FROM 'settle' THEN
    RAISE EXCEPTION 'unsupported settlement action';
  END IF;
  IF v_business_reference IS NULL OR v_business_reference = ''
     OR octet_length(v_business_reference) > 256 THEN
    RAISE EXCEPTION 'business_reference is required and bounded';
  END IF;
  IF v_escrow_account IS NULL
     OR v_escrow_account !~ '^escrow:[^\s]+$'
     OR octet_length(v_escrow_account) > 256 THEN
    RAISE EXCEPTION 'escrow_account is required and bounded';
  END IF;
  IF v_host_owner_user_id IS NULL OR v_host_owner_user_id = '' THEN
    RAISE EXCEPTION 'host owner authority is required';
  END IF;
  IF jsonb_typeof(v_body->'expected_state_version') IS DISTINCT FROM 'number'
     OR (v_body->>'expected_state_version') !~ '^[0-9]+$'
     OR jsonb_typeof(v_body->'amount_micros') IS DISTINCT FROM 'number'
     OR (v_body->>'amount_micros') !~ '^[1-9][0-9]*$' THEN
    RAISE EXCEPTION 'state version and amount must be bounded integers';
  END IF;
  BEGIN
    v_expected_state_version := (v_body->>'expected_state_version')::bigint;
    v_amount_micros := (v_body->>'amount_micros')::bigint;
  EXCEPTION
    WHEN numeric_value_out_of_range THEN
      RAISE EXCEPTION 'state version or amount exceeds bigint';
  END;
  IF jsonb_typeof(v_postings) IS DISTINCT FROM 'array'
     OR jsonb_array_length(v_postings) < 2
     OR jsonb_array_length(v_postings) > 16 THEN
    RAISE EXCEPTION 'postings must contain between 2 and 16 entries';
  END IF;

  BEGIN
    SELECT bool_or(
             entry->>'account' IS NULL
             OR octet_length(entry->>'account') > 256
             OR NOT (
               entry->>'account' = 'treasury'
               OR entry->>'account' ~ '^(user|escrow|collateral):[^\s]+$'
             )
             OR jsonb_typeof(entry->'delta_micros') IS DISTINCT FROM 'number'
             OR (entry->>'delta_micros') !~ '^-?[0-9]+$'
           )
      INTO v_bad_account
      FROM jsonb_array_elements(v_postings) AS entry;
    SELECT coalesce(sum((entry->>'delta_micros')::bigint), 0)
      INTO v_fee
      FROM jsonb_array_elements(v_postings) AS entry
     WHERE entry->>'account' = 'treasury';
  EXCEPTION
    WHEN numeric_value_out_of_range THEN
      RAISE EXCEPTION 'posting delta exceeds bigint';
  END;
  IF coalesce(v_bad_account, true) THEN
    RAISE EXCEPTION 'posting account or integer delta is invalid';
  END IF;
  SELECT coalesce(sum((entry->>'delta_micros')::bigint), 0)
    INTO v_escrow_delta
    FROM jsonb_array_elements(v_postings) AS entry
   WHERE entry->>'account' = v_escrow_account;
  SELECT coalesce(sum((entry->>'delta_micros')::bigint), 0)
    INTO v_seller_delta
    FROM jsonb_array_elements(v_postings) AS entry
   WHERE entry->>'account' = 'user:' || v_host_owner_user_id;
  IF v_fee <= 0
     OR v_escrow_delta <> -v_amount_micros
     OR v_seller_delta <> v_amount_micros - v_fee
     OR EXISTS (
       SELECT 1
         FROM jsonb_array_elements(v_postings) AS entry
        WHERE entry->>'account' NOT IN (
          v_escrow_account,
          'user:' || v_host_owner_user_id,
          'treasury'
        )
     ) THEN
    RAISE EXCEPTION 'postings do not match the canonical spot adapter';
  END IF;

  RETURN QUERY
    SELECT applied.status, applied.tx_id
      FROM market.apply_tx(
        v_tenant_id,
        v_idempotency_key,
        v_sha256,
        v_memo,
        v_postings
      ) AS applied;
END
$function$;

CREATE FUNCTION market.assert_drained(p_account text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, market, pg_temp
AS $function$
DECLARE
  v_balance bigint;
BEGIN
  SELECT b.balance_micros
    INTO v_balance
    FROM market.balances AS b
   WHERE b.account = p_account;
  IF coalesce(v_balance, 0) <> 0 THEN
    RAISE EXCEPTION 'account % not drained: %', p_account, v_balance;
  END IF;
END
$function$;

ALTER SCHEMA market OWNER TO tinyassets_fixture_market_owner;
ALTER TABLE market.transactions OWNER TO tinyassets_fixture_market_owner;
ALTER TABLE market.postings OWNER TO tinyassets_fixture_market_owner;
ALTER TABLE market.balances OWNER TO tinyassets_fixture_market_owner;
ALTER SEQUENCE market.transactions_tx_id_seq OWNER TO tinyassets_fixture_market_owner;
ALTER SEQUENCE market.postings_posting_id_seq OWNER TO tinyassets_fixture_market_owner;
ALTER FUNCTION market.apply_tx(text, text, text, text, jsonb)
  OWNER TO tinyassets_fixture_market_owner;
ALTER FUNCTION market.apply_settlement(bytea, text)
  OWNER TO tinyassets_fixture_market_owner;
ALTER FUNCTION market.assert_drained(text)
  OWNER TO tinyassets_fixture_market_owner;

REVOKE ALL ON SCHEMA market FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA market FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA market FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA market FROM PUBLIC;
REVOKE ALL ON SCHEMA market FROM tinyassets_fixture_app;
REVOKE ALL ON ALL TABLES IN SCHEMA market FROM tinyassets_fixture_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA market FROM tinyassets_fixture_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA market FROM tinyassets_fixture_app;

GRANT USAGE ON SCHEMA market TO tinyassets_fixture_settlement;
GRANT EXECUTE ON FUNCTION market.apply_settlement(bytea, text)
  TO tinyassets_fixture_settlement;
