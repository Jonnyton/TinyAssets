-- 007 — Capacity forwards (Track E Wave 4).
-- Table per the Track E spec, with the bucket-boundary rule enforced in-schema
-- where SQL can express it. tokens_requested is NON-NEGOTIABLE (adversarial
-- review finding B-1: settling against raw size makes buyer no-show griefing
-- profitable; obligation is min(requested, size)).
-- The pure module tinyassets/paid_market/forwards.py remains the settlement
-- oracle: the settle RPC calls its math, never reimplements it.

CREATE TABLE IF NOT EXISTS public.forwards (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_user_id    uuid NOT NULL REFERENCES public.users(user_id),
  daemon_id         text NOT NULL,
  capability_id     text NOT NULL REFERENCES public.capabilities(capability_id),
  bucket_start      timestamptz NOT NULL,
  bucket_hours      int NOT NULL CHECK (bucket_hours IN (8, 24, 168)),
  size_mtok         int NOT NULL CHECK (size_mtok IN (1, 10, 100)),
  price_micros_per_mtok bigint NOT NULL CHECK (price_micros_per_mtok > 0),
  -- Bounds mirror forwards.py MIN_COLLATERAL_PCT/MAX_COLLATERAL_PCT: a row the
  -- settlement oracle would refuse must not be persistable.
  collateral_pct    int NOT NULL DEFAULT 20 CHECK (collateral_pct BETWEEN 5 AND 100),
  collateral_status text NOT NULL DEFAULT 'none'
                      CHECK (collateral_status IN ('none','held','released','slashed')),
  state             text NOT NULL DEFAULT 'open'
                      CHECK (state IN ('open','sold','delivering','delivered',
                                       'settled','expired','defaulted')),
  buyer_user_id     uuid NULL REFERENCES public.users(user_id),
  tokens_requested  bigint NOT NULL DEFAULT 0 CHECK (tokens_requested >= 0),
  tokens_delivered  bigint NOT NULL DEFAULT 0 CHECK (tokens_delivered >= 0),
  created_at        timestamptz NOT NULL DEFAULT now(),

  -- Bucket boundaries (UTC): whole hour always; 8h blocks land on 00/08/16;
  -- days land on midnight; weeks land on Monday midnight (ISO dow 1).
  CONSTRAINT forwards_bucket_whole_hour CHECK (
    date_trunc('hour', bucket_start) = bucket_start
  ),
  CONSTRAINT forwards_bucket_alignment CHECK (
    CASE bucket_hours
      WHEN 8   THEN extract(hour  FROM bucket_start AT TIME ZONE 'UTC')::int % 8 = 0
      WHEN 24  THEN extract(hour  FROM bucket_start AT TIME ZONE 'UTC')::int = 0
      WHEN 168 THEN extract(hour  FROM bucket_start AT TIME ZONE 'UTC')::int = 0
               AND  extract(isodow FROM bucket_start AT TIME ZONE 'UTC')::int = 1
    END
  )
  -- 28-day sellable horizon is a POST-time rule (moving target) — enforced in
  -- the post RPC via buckets.validate_bucket_start, not as a table CHECK.
);

CREATE INDEX IF NOT EXISTS forwards_book
  ON public.forwards (capability_id, bucket_start, state, price_micros_per_mtok);
CREATE INDEX IF NOT EXISTS forwards_seller ON public.forwards (seller_user_id);
CREATE INDEX IF NOT EXISTS forwards_buyer
  ON public.forwards (buyer_user_id) WHERE buyer_user_id IS NOT NULL;
-- Settlement sweep hot path: everything sold/delivering whose bucket has ended.
CREATE INDEX IF NOT EXISTS forwards_settle_sweep
  ON public.forwards (bucket_start, state)
  WHERE state IN ('sold','delivering','delivered');
