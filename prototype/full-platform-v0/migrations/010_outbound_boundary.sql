-- 010 - Non-value-moving outbound connection resources and universe grants.
-- FOUNDER-GATED: fixture schema only; this migration moves no value.

CREATE SCHEMA IF NOT EXISTS boundary;

CREATE TABLE boundary.connections (
  connection_id    text PRIMARY KEY,
  owner_user_id    text NOT NULL CHECK (owner_user_id <> ''),
  connection_class text NOT NULL CHECK (connection_class <> ''),
  scopes           jsonb NOT NULL CHECK (jsonb_typeof(scopes) = 'array'),
  provider         text NOT NULL CHECK (provider <> ''),
  destination      text NOT NULL CHECK (destination <> ''),
  credential_ref   text NOT NULL CHECK (credential_ref <> ''),
  revoked_at       timestamptz
);

CREATE TABLE boundary.connection_grants (
  grant_id       text PRIMARY KEY,
  connection_id text NOT NULL REFERENCES boundary.connections(connection_id),
  owner_user_id  text NOT NULL CHECK (owner_user_id <> ''),
  universe_id    text NOT NULL CHECK (universe_id <> ''),
  granted_at     timestamptz NOT NULL DEFAULT now(),
  revoked_at     timestamptz
);
CREATE INDEX connection_grants_resolution
  ON boundary.connection_grants(owner_user_id, universe_id)
  WHERE revoked_at IS NULL;

CREATE TABLE boundary.connector_artifacts (
  artifact_id           text PRIMARY KEY,
  owner_user_id         text NOT NULL CHECK (owner_user_id <> ''),
  connector_definition  jsonb NOT NULL
    CHECK (jsonb_typeof(connector_definition) = 'object'),
  mcp_client_config     jsonb NOT NULL
    CHECK (jsonb_typeof(mcp_client_config) = 'object'),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE boundary.connector_artifact_edges (
  parent_artifact_id text NOT NULL
    REFERENCES boundary.connector_artifacts(artifact_id),
  child_artifact_id  text NOT NULL
    REFERENCES boundary.connector_artifacts(artifact_id),
  remixed_by_user_id text NOT NULL CHECK (remixed_by_user_id <> ''),
  created_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (parent_artifact_id, child_artifact_id),
  CHECK (parent_artifact_id <> child_artifact_id)
);

REVOKE ALL ON SCHEMA boundary FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA boundary FROM PUBLIC;
