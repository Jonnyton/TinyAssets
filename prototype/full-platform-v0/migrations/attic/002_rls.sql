-- RLS per #25 schema spec §2 — simplified for v0 prototype.
--
-- In production: Supabase Auth puts JWT claims in request.jwt.claims at GUC.
-- In v0: we set current_setting('app.current_user_id') directly via SET LOCAL.
-- The auth.uid() wrapper below matches either path — v0 reads app.current_user_id,
-- production reads request.jwt.claims.sub. Same call site, different source.

-- v0 auth.uid() shim — reads from app.current_user_id GUC (SET LOCAL by caller).
CREATE SCHEMA IF NOT EXISTS auth;

CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid;
  $$;

-- -----------------------------------------------------------------------
-- RLS on nodes
-- -----------------------------------------------------------------------
ALTER TABLE public.nodes ENABLE ROW LEVEL SECURITY;

-- Owners see everything they own
CREATE POLICY nodes_select_owner ON public.nodes
  FOR SELECT TO PUBLIC
  USING (auth.uid() = owner_user_id);

-- Non-owners see public-concept-visibility rows
CREATE POLICY nodes_select_public ON public.nodes
  FOR SELECT TO PUBLIC
  USING (concept_visibility = 'public');

-- Inserts/updates/deletes: owner-only
CREATE POLICY nodes_insert_owner ON public.nodes
  FOR INSERT TO PUBLIC
  WITH CHECK (auth.uid() = owner_user_id);

CREATE POLICY nodes_update_owner ON public.nodes
  FOR UPDATE TO PUBLIC
  USING (auth.uid() = owner_user_id);

CREATE POLICY nodes_delete_owner ON public.nodes
  FOR DELETE TO PUBLIC
  USING (auth.uid() = owner_user_id);

-- -----------------------------------------------------------------------
-- RLS on artifact_field_visibility — owner-only
-- -----------------------------------------------------------------------
ALTER TABLE public.artifact_field_visibility ENABLE ROW LEVEL SECURITY;

CREATE POLICY afv_owner_only ON public.artifact_field_visibility
  FOR ALL TO PUBLIC
  USING (
    EXISTS (
      SELECT 1 FROM public.nodes n
      WHERE n.node_id = artifact_field_visibility.artifact_id
        AND artifact_field_visibility.artifact_kind = 'node'
        AND n.owner_user_id = auth.uid()
    )
  );

-- -----------------------------------------------------------------------
-- Field-stripping function for non-owner reads
-- -----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.strip_private_fields(
  p_concept     jsonb,
  p_artifact_id uuid,
  p_kind        text
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE
  v_out jsonb := p_concept;
  v_path text;
BEGIN
  FOR v_path IN
    SELECT field_path
    FROM public.artifact_field_visibility
    WHERE artifact_id = p_artifact_id
      AND artifact_kind = p_kind
      AND visibility = 'private'
  LOOP
    -- #- operator removes the path from the jsonb value.
    -- Paths like "/concept/example_company" → ['concept','example_company'].
    v_out := v_out #- string_to_array(trim(leading '/' from v_path), '/');
  END LOOP;
  RETURN v_out;
END;
$$;
