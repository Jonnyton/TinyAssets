## RENAMED Requirements

- FROM: `Public Canary And Directory Review Surface`
- TO: `Public Canary And Canonical Review Surface`
- FROM: `Published registry metadata follows the current versioned directory catalog`
- TO: `Published registry metadata follows canonical MCP`

## MODIFIED Requirements

### Requirement: Public Canary And Canonical Review Surface
The platform SHALL expose `https://tinyassets.io/mcp` as its sole remote
user-facing MCP endpoint. Its advertised set SHALL be exactly
`{read_graph, write_graph, run_graph, read_page, write_page, converse,
get_status}`. Registry and hosted-chatbot review metadata SHALL bind to this
endpoint rather than an alternate directory product.

The platform SHALL preserve the stdlib-only public canary
(`scripts/mcp_public_canary.py`) whose `--assert-handles` mode performs a full
handshake, reads `tools/list`, and exits 4 with missing/extra sets on every
exact-seven mismatch. The separate lightweight `scripts/uptime_canary.py`
obligation SHALL remain intact.

Public status returned through `read_graph(target=status)` or `get_status`
SHALL be a typed, fail-closed allowlist projection that excludes operator
diagnostics, activity-log content, identities, sessions, filesystem paths,
policy hashes, internal exceptions, and debug fields. The exact output
authority is `public-status-v1`:

```json
{
  "$id": "https://tinyassets.io/schemas/public-status-v1.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "public_status_schema_version",
    "status",
    "founder_home_state",
    "universe_exists",
    "provider_state",
    "daemon_state",
    "storage_pressure",
    "queue",
    "next_actions",
    "privacy_note",
    "error"
  ],
  "properties": {
    "public_status_schema_version": {"const": 1},
    "status": {
      "enum": [
        "ready",
        "setup_required",
        "degraded",
        "unavailable",
        "access_denied"
      ]
    },
    "founder_home_state": {"enum": ["bound", "unbound", "unknown"]},
    "universe_exists": {"type": ["boolean", "null"]},
    "provider_state": {"enum": ["available", "setup_required", "unknown"]},
    "daemon_state": {"enum": ["healthy", "degraded", "unknown"]},
    "storage_pressure": {"enum": ["ok", "warn", "critical", "unknown"]},
    "queue": {
      "type": "object",
      "additionalProperties": false,
      "required": ["pending", "running", "stale"],
      "properties": {
        "pending": {"type": ["integer", "null"], "minimum": 0},
        "running": {"type": ["integer", "null"], "minimum": 0},
        "stale": {"type": ["integer", "null"], "minimum": 0}
      }
    },
    "next_actions": {
      "type": "array",
      "uniqueItems": true,
      "maxItems": 5,
      "items": {
        "enum": [
          "start_conversation",
          "configure_provider",
          "select_or_create_universe",
          "retry_status",
          "reauthenticate",
          "contact_support"
        ]
      }
    },
    "privacy_note": {
      "const": "Public status omits operator logs, identities, paths, hashes, exceptions, and debug data."
    },
    "error": {
      "anyOf": [
        {"type": "null"},
        {
          "oneOf": [
            {
              "type": "object",
              "additionalProperties": false,
              "required": ["code", "message", "retryable"],
              "properties": {
                "code": {"const": "access_denied"},
                "message": {"const": "Status access was denied."},
                "retryable": {"const": false}
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "required": ["code", "message", "retryable"],
              "properties": {
                "code": {"const": "status_source_unavailable"},
                "message": {"const": "Public status is temporarily unavailable."},
                "retryable": {"const": true}
              }
            },
            {
              "type": "object",
              "additionalProperties": false,
              "required": ["code", "message", "retryable"],
              "properties": {
                "code": {"const": "status_projection_failed"},
                "message": {"const": "Public status could not be projected safely."},
                "retryable": {"const": true}
              }
            }
          ]
        }
      ]
    }
  }
}
```

The projector SHALL support four upstream shapes and always emit the schema
above:

- a full status object maps `universe_exists` directly when boolean;
  `founder_home_state` is `bound` only when trusted request context proves an
  authenticated founder omitted `universe_id` and the resolver selected that
  founder's complete bound home; an explicit target, anonymous/dev default, or
  missing trusted binding context maps to `unknown`;
- `provider_state` is `available` only when
  `active_host.llm_endpoint_bound` is one of `ollama`, `anthropic`, `codex`,
  `claude`, `xai`, `gemini`, or `groq`; it is `setup_required` for `unset`
  and `unknown` otherwise;
- `daemon_state` is `healthy` only when `supervisor_liveness` is an object
  whose `warnings` and `stale_running_tasks` arrays are both empty; it is
  `degraded` when either array is non-empty and `unknown` when those shapes are
  absent or invalid;
- `storage_pressure` copies only exact `ok`, `warn`, or `critical` from
  `storage_utilization.pressure_level` and otherwise becomes `unknown`;
- queue `pending` and `running` copy only non-negative integers from
  `supervisor_liveness.queue_state`; `stale` is only the length of the
  `stale_running_tasks` array; missing or invalid values become null;
- full status is `setup_required` when provider setup is required or the
  trusted authenticated context reports an unbound founder home,
  `degraded` when daemon/storage is degraded or unknown, and `ready` only when
  the target universe exists, the provider is available, the daemon is
  healthy, storage pressure is `ok`, and founder-home state is either verified
  `bound` or legitimately `unknown` for an explicit/anonymous target;
- first-contact/no-home maps to `status=setup_required`,
  `founder_home_state=unbound`, and
  `next_actions=["start_conversation"]`;
- access denial maps to `status=access_denied` and the fixed
  `access_denied` error;
- configuration/source failure maps to `status=unavailable` and the fixed
  `status_source_unavailable` error.

Malformed JSON, a non-object source, an unrecognized root response shape, or a
projection exception SHALL return the same fully populated schema with
`status=unavailable`, unknown/null scalar values, empty `next_actions`, and the
fixed `status_projection_failed` error. Unknown top-level and nested source
keys SHALL never be copied. No source string, identifier, list entry,
exception, path, hash, or diagnostic text may pass through this projection.
`next_actions` SHALL be derived only from output enums: unbound founder home
adds `start_conversation`; `universe_exists=false` adds
`select_or_create_universe`; provider setup adds `configure_provider`; an
unavailable retryable error adds
`retry_status`; access denial adds `reauthenticate`; no upstream free text
becomes an action.

After the reviewed migration gates in this change pass, `/mcp-directory` and
every versioned `/mcp-directory*` catalog route SHALL be unmounted. The
platform SHALL NOT redirect, proxy, or silently translate the retired path.

#### Scenario: Canary fails on advertised-handle drift
- **WHEN** canonical `/mcp` is missing a required handle or advertises a handle outside the exact seven
- **THEN** `scripts/mcp_public_canary.py --assert-handles` exits 4 and reports the missing and extra sets
- **AND** the separate lightweight uptime canary remains available

#### Scenario: Public status is projected safely
- **WHEN** any caller reads status through canonical `/mcp`
- **THEN** the result validates against exact `public-status-v1` with no additional properties at any depth
- **AND** each full, first-contact, access-denied, and source-failure shape maps to its defined bounded representation
- **AND** new or unparseable upstream fields fail closed rather than falling back to raw status text
- **AND** sentinel unknown keys and nested values are absent from the serialized result
- **AND** operator-only evidence remains unavailable through public MCP status

#### Scenario: Retired directory route is absent
- **WHEN** a client calls `/mcp-directory` or a versioned descendant after the cutover
- **THEN** no MCP transport or catalog is mounted at that path
- **AND** the response does not redirect or proxy the caller to `/mcp`

### Requirement: Cloudflare Worker Public Front Door

`https://tinyassets.io/mcp` SHALL be the only public user-facing MCP URL. A
Cloudflare Worker on the `tinyassets.io/mcp*` route SHALL proxy only canonical
`/mcp` traffic to the Access-gated tunnel origin `mcp.tinyassets.io`, injecting
the CF Access service-token headers from Worker environment secrets. The Worker
SHALL stream SSE bodies without buffering, preserve request headers and method,
and map an unreachable tunnel or upstream `5xx` to an explicit `502` JSON body.
After cutover it SHALL NOT route, redirect, proxy, or translate
`/mcp-directory*`. `mcp.tinyassets.io` is an internal origin and MUST NOT be
presented as user-facing.

#### Scenario: Worker proxies canonical MCP only
- **WHEN** a client request arrives at `tinyassets.io/mcp`
- **THEN** the Worker rewrites `Host` to `mcp.tinyassets.io`, adds its service-token headers, and forwards method, body stream, and non-hop-by-hop headers
- **AND** the same Worker has no route or translation for `/mcp-directory*`

#### Scenario: SSE bodies stream without buffering
- **WHEN** the tunnel origin returns a `text/event-stream` response
- **THEN** the Worker returns the upstream stream without materializing it

#### Scenario: Tunnel failure surfaces as an explicit 502
- **WHEN** the tunnel origin returns a `5xx` status or is unreachable
- **THEN** the Worker responds `502` with a `bad_gateway` JSON body rather than falling through to another origin

### Requirement: Published registry metadata follows canonical MCP

The checked-in MCP Registry manifest SHALL advertise
`https://tinyassets.io/mcp`. Repository tests and packaging CI SHALL fail when
`packaging/registry/server.json` differs from deterministic canonical runtime
metadata. The generator SHALL run directly from a clean repository checkout,
and each externally published metadata change SHALL advance the manifest
version.

#### Scenario: Canonical catalog change makes stale metadata fail
- **WHEN** canonical endpoint or exact-seven runtime metadata changes without regenerating `packaging/registry/server.json`
- **THEN** focused artifact-equality and packaging checks fail

#### Scenario: Published registry remote is canonical and reachable
- **WHEN** a Registry version is proposed for publication
- **THEN** its remote URL is exactly `https://tinyassets.io/mcp`
- **AND** a read-only Streamable-HTTP handshake lists the canonical exact-seven catalog

### Requirement: Registered tools publish exact discoverability and behavior metadata

The system SHALL attach the following title, tag set, and four MCP behavior
hints to every currently registered tool. In the hint columns, `T` means true
and `F` means false, ordered as read-only, destructive, idempotent, and
open-world:

| Tool | Title | Tags | R | D | I | O |
|---|---|---|---:|---:|---:|---:|
| `read_graph` | `Read Graph` | `graph`, `read`, `tinyassets` | T | F | T | F |
| `write_graph` | `Write Graph` | `graph`, `tinyassets`, `write` | F | T | F | T |
| `run_graph` | `Run Graph` | `graph`, `run`, `tinyassets` | F | T | F | T |
| `read_page` | `Read Page` | `page`, `read`, `tinyassets`, `wiki` | T | F | T | F |
| `write_page` | `Write Page` | `page`, `tinyassets`, `wiki`, `write` | F | T | F | T |
| `converse` | `Talk With Your Universe` | `relay`, `tinyassets`, `universe` | F | F | F | T |
| `universe` | `Universe Operations` | `agent-workflow`, `ai-builder`, `collaboration`, `custom-ai`, `daemon`, `general-purpose`, `tinyassets`, `universe`, `universe-builder`, `workflow-builder` | F | F | F | T |
| `community_change_context` | `Community Change Context` | `change-loop`, `community`, `github`, `plan`, `pull-request`, `review`, `tinyassets` | T | F | T | T |
| `extensions` | `Graph Extensions` | `customization`, `extensions`, `nodes`, `plugins` | F | F | F | T |
| `goals` | `Goals` | `community`, `discovery`, `goals`, `intent` | F | F | F | T |
| `gates` | `Outcome Gates` | `community`, `gates`, `impact`, `leaderboard`, `outcomes` | F | F | F | T |
| `wiki` | `Wiki Knowledge Base` | `drafts`, `knowledge`, `pages`, `research`, `wiki` | F | T | F | T |
| `get_status` | `Daemon Status + Routing Evidence` | `confidential-tier`, `privacy`, `routing`, `status`, `tinyassets`, `verification` | T | F | T | F |

These hints SHALL remain descriptive metadata rather than authorization
enforcement. The implementations and permission middleware retain authority
over mutation, visibility, ownership, and action-specific validation.

#### Scenario: Raw registry listing carries exact metadata
- **WHEN** the server registry is listed without deprecated-tool visibility filtering
- **THEN** every registered tool has the exact title, tag set, and four hint values in the table

#### Scenario: Behavior hints do not grant authority
- **WHEN** a tool's metadata marks it non-destructive or open-world
- **THEN** that metadata does not bypass authentication, ownership, write gates, or action-specific validation

## ADDED Requirements

### Requirement: Canonical MCP Is Safe For Reviewed Hosts
Canonical `/mcp` SHALL publish neutral server instructions, truthful bounded
tool descriptions, conservative annotations, and per-tool security schemes
that match runtime enforcement.

Instructions SHALL describe tool relevance without requiring an unsolicited
tool call, importing another prompt, impersonating a universe, or forcing
verbatim relay. `converse` SHALL be selected only from explicit user intent.

Protected Resource Metadata SHALL identify
`resource=https://tinyassets.io/mcp` and SHALL advertise only the AuthKit-
issuable OIDC scopes `openid`, `profile`, `email`, and `offline_access`.
Internal `tinyassets.*` capabilities SHALL NOT be advertised as OAuth scopes.
The serialized `tools/list` result SHALL carry this exact scheme table in both
the standard `securitySchemes` field and ChatGPT's back-compat
`_meta["securitySchemes"]` mirror; the two arrays SHALL be byte-equivalent
after canonical JSON serialization:

| Handle | Exact `securitySchemes` |
|---|---|
| `read_graph` | `[{"type":"noauth"},{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |
| `read_page` | `[{"type":"noauth"},{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |
| `get_status` | `[{"type":"noauth"},{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |
| `write_graph` | `[{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |
| `write_page` | `[{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |
| `run_graph` | `[{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |
| `converse` | `[{"type":"oauth2","scopes":["openid","profile","email","offline_access"]}]` |

Bearer-token validation SHALL pin RS256, issuer, audience equal to the
registered resource, expiry, and a non-anonymous subject. OAuth scopes
authenticate the client session; they SHALL NOT replace server-side authority.
Before an effect, the Resource Server SHALL separately enforce the subject's
founder grants/capabilities plus visibility, ownership, and action/object ACLs.
An `org_id` claim MAY be retained as identity metadata but SHALL NOT be treated
as a tenant authorization boundary without a separate reviewed contract.

Missing or invalid credentials on a pure identity-gated handle SHALL produce
HTTP `401` with `WWW-Authenticate` before dispatch. An auth-required result
discovered inside a mixed public/private router SHALL include
`_meta["mcp/www_authenticate"]` where the host uses lazy/tool-level linking.
Wire-level tests SHALL inspect serialized metadata and responses rather than
source objects alone.

Annotations and descriptions SHALL conservatively cover every target/action
behind a router. Public publication sets the open-world hint. Overwrite,
replacement, or irreversible paths set the destructive hint. Persistence,
provider/data sharing, requester-funded compute, cost, confirmation,
reversibility, and uncertain outcomes SHALL be disclosed where applicable.
Errors and results SHALL be bounded and secret-free.

The reviewed canonical annotation contract SHALL be:

| Handle | `readOnlyHint` | `destructiveHint` | `idempotentHint` | `openWorldHint` |
|---|---:|---:|---:|---:|
| `read_graph` | true | false | true | false |
| `read_page` | true | false | true | false |
| `write_graph` | false | true | false | true |
| `write_page` | false | true | false | true |
| `run_graph` | false | true | false | true |
| `converse` | false | false | false | true |
| `get_status` | true | false | true | false |

`run_graph` is open-world and destructive because the advertised envelope may
execute declared external or irreversible nodes. `converse` is open-world
because it can route data to requester-authorized model providers and persist
learning, but its current governed turn contract exposes no delete/overwrite
operation. `get_status` is a pure, idempotent read and never creates or binds a
home universe; first-contact birth belongs only to authenticated `converse`.
A future target/action that changes any envelope SHALL update and re-review the
public contract before deployment.

#### Scenario: Server instructions do not force use
- **WHEN** a host reads canonical server instructions
- **THEN** the instructions explain capabilities and selection criteria without ordering the model to call a tool on every opening message
- **AND** universe conversation or personification requires explicit user intent

#### Scenario: OAuth metadata matches enforcement
- **WHEN** a host scans the seven canonical tools
- **THEN** serialized `tools/list` metadata contains the exact per-tool scheme table above in both `securitySchemes` and its identical `_meta["securitySchemes"]` mirror using only AuthKit-issuable OIDC scopes
- **AND** Protected Resource Metadata identifies `https://tinyassets.io/mcp`
- **AND** bearer validation and server-side action/object authority are tested as separate gates
- **AND** a missing or invalid credential for a pure identity-gated handle produces HTTP `401` plus `WWW-Authenticate` before provider selection or mutation
- **AND** mixed-router lazy-linking responses include `_meta["mcp/www_authenticate"]` where the host contract requires it

#### Scenario: Router risk metadata is conservative
- **WHEN** a host scans canonical `/mcp`
- **THEN** every handle's serialized annotations equal the reviewed table above
- **AND** descriptions disclose applicable publication, overwrite, persistence, provider, cost, confirmation, reversibility, and uncertain-outcome behavior
- **AND** a low-risk action in a router does not justify understating the router's highest advertised risk

#### Scenario: Privacy disclosure matches runtime
- **WHEN** canonical `/mcp` is submitted to a reviewed host
- **THEN** current privacy materials disclose identity processing, activity evidence, retention/deletion, public commons publication, and BYOC/third-party provider routing
- **AND** returned tool data does not exceed those documented purposes
