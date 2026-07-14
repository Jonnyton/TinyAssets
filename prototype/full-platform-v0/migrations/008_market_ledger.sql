-- 008 — Double-entry market ledger + THE single money-movement RPC.
-- ⚠ FOUNDER-GATED: this migration implements the ledger-coexistence decision
-- (crash-test findings §2a/§3). Do not apply until the founder signs off.
--
-- Decision it implements: public.ledger (001) is FROZEN as the v1 historical
-- single-entry table ("v1 shape must outlive token-launch migration
-- byte-for-byte" — preserved). The bundle's double-entry, zero-sum,
-- integer-micros ledger (tinyassets/paid_market/ledger.py) persists here.
--
-- HARD RULE this schema enforces: every money movement in the market goes
-- through market.apply_tx() and NOTHING ELSE. Application code never
-- computes a balance and writes it. The pure ledger.py stays the validation
-- oracle and the executable spec; this RPC is its one transport.
--
-- Concurrency proof-of-need: 8 unlocked threads against the pure ledger
-- created 278 units from nothing (lost updates); single-writer did 1M tx
-- with zero drift. Serialization is not optional.

CREATE SCHEMA IF NOT EXISTS market;

CREATE TABLE IF NOT EXISTS market.transactions (
  tx_id            bigserial PRIMARY KEY,
  idempotency_key  text NOT NULL UNIQUE,   -- deterministic key from the effect layer
  memo             text NOT NULL DEFAULT '',
  at               timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market.postings (
  posting_id   bigserial PRIMARY KEY,
  tx_id        bigint NOT NULL REFERENCES market.transactions(tx_id),
  account      text   NOT NULL,        -- 'user:<id>'|'escrow:<id>'|'collateral:<id>'
                                       -- |'pool:<id>'|'treasury'|'external:<name>'
  delta_micros bigint NOT NULL CHECK (delta_micros <> 0),
  CONSTRAINT postings_account_shape CHECK (
    account = 'treasury' OR account ~ '^(user|escrow|collateral|pool|external):[^\s]+$'
  )
);
CREATE INDEX IF NOT EXISTS postings_account ON market.postings (account, tx_id);
CREATE INDEX IF NOT EXISTS postings_tx      ON market.postings (tx_id);

CREATE TABLE IF NOT EXISTS market.balances (
  account        text PRIMARY KEY,
  balance_micros bigint NOT NULL DEFAULT 0,
  -- external:* are boundary contra accounts and MAY go negative (their
  -- negative balance is the audit total of net inflows). Everything else
  -- may not — same rule as ledger.py, enforced here so a bypassing write
  -- still cannot overdraw.
  CONSTRAINT balances_no_internal_overdraft CHECK (
    balance_micros >= 0 OR account LIKE 'external:%'
  )
);

-- ---------------------------------------------------------------------------
-- market.apply_tx — the ONLY writer. SECURITY DEFINER; direct table
-- INSERT/UPDATE is revoked from application roles below.
--
-- p_postings: jsonb array of {"account": text, "delta_micros": bigint}.
-- Returns tx_id. EXACTLY-ONCE: replay with the same idempotency_key returns
-- the original tx_id without re-applying (caller treats both cases the same).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION market.apply_tx(
  p_idempotency_key text,
  p_memo            text,
  p_postings        jsonb
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_tx_id    bigint;
  v_sum      bigint;
  v_rec      record;
BEGIN
  IF p_idempotency_key IS NULL OR length(p_idempotency_key) = 0 THEN
    RAISE EXCEPTION 'idempotency_key required';
  END IF;
  IF jsonb_typeof(p_postings) <> 'array' OR jsonb_array_length(p_postings) < 2 THEN
    RAISE EXCEPTION 'postings must be an array of >= 2 entries';
  END IF;

  -- (1) Exactly-once seam. Claim the key; on replay return the recorded tx.
  INSERT INTO market.transactions (idempotency_key, memo)
  VALUES (p_idempotency_key, coalesce(p_memo, ''))
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING tx_id INTO v_tx_id;
  IF v_tx_id IS NULL THEN
    SELECT tx_id INTO v_tx_id FROM market.transactions
      WHERE idempotency_key = p_idempotency_key;
    RETURN v_tx_id;  -- replay: effect already applied (or applying in a
                     -- committed sibling); never apply twice.
  END IF;

  -- (2) Zero-sum: money moves, it is never created or destroyed.
  SELECT coalesce(sum((e->>'delta_micros')::bigint), 0) INTO v_sum
    FROM jsonb_array_elements(p_postings) e;
  IF v_sum <> 0 THEN
    RAISE EXCEPTION 'postings do not zero-sum (sum=%)', v_sum;
  END IF;

  -- (3) Net per account, ensure balance rows exist, then LOCK them in
  --     account-name order (stable order prevents deadlock between
  --     concurrent transactions touching overlapping account sets).
  DROP TABLE IF EXISTS _net;  -- same-session/same-tx reentrancy safety
  CREATE TEMP TABLE _net ON COMMIT DROP AS
    SELECT e->>'account' AS account,
           sum((e->>'delta_micros')::bigint) AS delta
      FROM jsonb_array_elements(p_postings) e
     GROUP BY 1;

  INSERT INTO market.balances (account, balance_micros)
    SELECT account, 0 FROM _net
  ON CONFLICT (account) DO NOTHING;

  -- (4) Overdraft check against LOCKED balances, applied on the NET result
  --     so ordering inside a transaction cannot matter (same as ledger.py).
  FOR v_rec IN
    SELECT b.account, b.balance_micros, n.delta
      FROM market.balances b
      JOIN _net n USING (account)
     ORDER BY b.account
       FOR UPDATE OF b
  LOOP
    IF v_rec.account NOT LIKE 'external:%'
       AND v_rec.balance_micros + v_rec.delta < 0 THEN
      RAISE EXCEPTION 'overdraft on % (balance %, delta %) [%]',
        v_rec.account, v_rec.balance_micros, v_rec.delta, p_memo;
    END IF;
  END LOOP;

  -- (5) Apply: balances + full posting rows (original, un-netted entries —
  --     the audit trail preserves what the caller stated).
  UPDATE market.balances b
     SET balance_micros = b.balance_micros + n.delta
    FROM _net n
   WHERE b.account = n.account;

  INSERT INTO market.postings (tx_id, account, delta_micros)
    SELECT v_tx_id, e->>'account', (e->>'delta_micros')::bigint
      FROM jsonb_array_elements(p_postings) e;

  RETURN v_tx_id;
END;
$$;

-- Escrow drain audit (ledger.py assert_drained analogue) — call after any
-- settlement; a non-zero escrow is a caught fault, not a silent leak.
CREATE OR REPLACE FUNCTION market.assert_drained(p_account text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE v bigint;
BEGIN
  SELECT balance_micros INTO v FROM market.balances WHERE account = p_account;
  IF coalesce(v, 0) <> 0 THEN
    RAISE EXCEPTION 'account % not drained: %', p_account, v;
  END IF;
END;
$$;

-- (6) Lock the side doors: application roles cannot write tables directly.
REVOKE INSERT, UPDATE, DELETE ON market.transactions, market.postings,
  market.balances FROM PUBLIC;
-- grant EXECUTE on market.apply_tx / market.assert_drained to the app role
-- in the environment-specific grants file (role names differ per deploy).
