-- 011 — Actor-scoped Goal canonicals.
-- The parallel 010 migration owns public.goals and public.branch_versions.
-- This migration can land first: it creates the actor-scoped table now and
-- backfills only when the reserved 010 substrate is already present.
--
-- During transition, default writes update this table and
-- goals.canonical_branch_version_id. Readers prefer an exact scope_actor row,
-- then the empty default row, then the legacy Goal column.

CREATE TABLE public.goal_canonicals (
  goal_id           text NOT NULL,
  scope_actor       text NOT NULL DEFAULT '',
  branch_version_id text NOT NULL,
  set_at            timestamptz NOT NULL DEFAULT now(),
  set_by            text NOT NULL,
  PRIMARY KEY (goal_id, scope_actor)
);

CREATE INDEX goal_canonicals_branch_version
  ON public.goal_canonicals (branch_version_id);

DO $backfill$
BEGIN
  IF to_regclass('public.goals') IS NOT NULL THEN
    EXECUTE $sql$
      INSERT INTO public.goal_canonicals (
        goal_id,
        scope_actor,
        branch_version_id,
        set_at,
        set_by
      )
      SELECT
        goal_id::text,
        '',
        canonical_branch_version_id,
        updated_at,
        author::text
      FROM public.goals
      WHERE canonical_branch_version_id IS NOT NULL
      ON CONFLICT (goal_id, scope_actor) DO NOTHING
    $sql$;
  END IF;
END
$backfill$;
