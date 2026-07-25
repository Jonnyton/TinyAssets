-- 011 — Actor-scoped Goal canonicals.
-- Depends on the parallel 010 migration establishing public.goals and
-- public.branch_versions. Do not renumber this migration if 010 is absent.
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
ON CONFLICT (goal_id, scope_actor) DO NOTHING;
