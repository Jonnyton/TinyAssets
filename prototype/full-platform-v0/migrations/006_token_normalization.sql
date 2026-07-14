-- 006 — Token-normalized settlement (Track E Wave 3a).
-- CORRECTED vs the Track E doc: the doc says `ALTER TABLE public.request_inbox`,
-- but 001_core_tables.sql deliberately split the sketch's request_inbox into
-- public.requests (see 001 line ~104 comment). Altering request_inbox would
-- fail — or worse, tempt an executor to create a phantom table. Target is
-- public.requests.
-- Additive only. Idempotent. v1 rows untouched (new columns nullable).

ALTER TABLE public.requests
  ADD COLUMN IF NOT EXISTS tokens_in  bigint,   -- prompt tokens, reported at complete_request
  ADD COLUMN IF NOT EXISTS tokens_out bigint;   -- completion tokens produced

ALTER TABLE public.ledger
  ADD COLUMN IF NOT EXISTS tokens_in  bigint,
  ADD COLUMN IF NOT EXISTS tokens_out bigint,
  ADD COLUMN IF NOT EXISTS unit_price_micros_per_mtok bigint;
  -- derived at settle: integer micros; NEVER computed with floats.
  -- unit_price = (amount_micros * 1_000_000) / tokens_out, floored.

-- Rule (enforced in the complete_request RPC, not here): state='completed'
-- REQUIRES non-null token counts — fail-loud, no silent nulls. This file is
-- schema only; the RPC change ships with the Wave 2 transport work.

-- Settled-trade read path for the spot index (index.compute_spot_quote):
CREATE INDEX IF NOT EXISTS settlements_capability_settled_at
  ON public.settlements (settled_at DESC);
-- capability comes via join on requests; if quote latency needs it later,
-- denormalize capability_id onto settlements in a follow-up migration —
-- do NOT widen this one after it has been applied anywhere.
