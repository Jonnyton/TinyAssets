# MCPB Local Acceptance Record

What the local MCPB product's automated proof actually covers, and what it
does not. The local bundle and hosted `https://tinyassets.io/mcp` are two
products: evidence from one never satisfies the other's gate.

Machine-checked by `tests/test_packaging_build.py`. Freshness: verified
2026-07-25 on Windows 11 / Python 3.11 against this branch. Re-stamp this
file when the covered behavior changes.

## Proven

Reproduce with `python -m pytest tests/test_packaging_build.py`:

- **Staged artifact, not source.** `python packaging/mcpb/build_bundle.py`
  stages the live `tinyassets/` package, import-probes it in a subprocess,
  and fails the build when the staged manifest and the middleware-applied
  staged runtime catalogs differ.
- **Exactly seven handles.** The staged manifest and the staged runtime both
  declare `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
  `converse`, `get_status` — no hidden legacy fat tools.
- **Real stdio launch.** `server.py` is spawned with an isolated temporary
  data directory and driven over newline-delimited JSON-RPC on stdin/stdout;
  `initialize` returns `serverInfo.name == "TinyAssets"` and `tools/list`
  enumerates exactly those seven.
- **Required data directory fails closed.** A blank, missing, or
  non-directory `TINYASSETS_DATA_DIR` raises an actionable error before any
  transport starts. Without that guard `storage.data_dir()` would resolve an
  unset value to the platform default (`%APPDATA%/TinyAssets`,
  `~/.tinyassets`) and serve a directory the user never selected.
- **Optional default universe is validated then exported.** A blank host
  substitution is treated as unset; separators, a leading dot, or an
  unsubstituted `${...}` template are rejected before transport.
- **Provider-free.** `build_bundle.py`'s import and catalog probes and the
  stdio probes all strip provider credentials (`PROVIDER_CREDENTIAL_ENV`)
  from the environment they hand a subprocess, and no probe calls a tool —
  enumeration only. A green packaging gate cannot spend maintainer quota.

## Observed local auth posture

The bundle configures no auth: its manifest declares only
`TINYASSETS_DATA_DIR` and `UNIVERSE_SERVER_DEFAULT_UNIVERSE`, and the wrapper
introduces no environment of its own. Auth provider selection reads
`UNIVERSE_SERVER_AUTH` from the inherited environment
(`tinyassets/auth/provider.py`, `create_provider`), so with nothing
configured the staged runtime selects the no-auth `DevAuthProvider` — proven
by probing the staged runtime under exactly the bundle's environment.
Requests then run as the runtime's anonymous local actor, and an
uncredentialed client completes `initialize` and enumerates the catalog. The
product's boundary is the local OS process plus the user-selected data
directory — nothing else.

Two honest qualifications. Enumeration is not an authorization check, so
per-call gating behavior is not established by that handshake. And a host
that exports `UNIVERSE_SERVER_AUTH` into the bundle's process would change
the selected provider; that is an environment posture the package neither
configures nor claims.

Sharing handle names with hosted `/mcp` is catalog parity.
It is **not** identity parity: no hosted isolation, no WorkOS subject, no
OAuth scopes, no founder grants. Any future local identity boundary requires
its own reviewed package change.

## Not proven

- **Host install path.** The proof spawns `server.py` directly. Installation
  through a real MCPB host (`uv run` via the manifest's `mcp_config`,
  user-config prompts, `.mcpb` pack/validate through
  `npx @anthropic-ai/mcpb`) is separate evidence and is not asserted here.
- **Tool execution.** Nothing beyond enumeration runs. No `converse`,
  `run_graph`, or other result payload is exercised locally, so
  provider-backed behavior — and every per-call permission, visibility, and
  ownership check — is unproven by this record.
- **Actor-dependent behavior.** Because the local actor is anonymous with no
  founder identity, permission-gated, visibility-gated, ownership-gated, and
  founder-grant behavior is unproven locally and may legitimately differ from
  the hosted product. Do not infer hosted behavior from a local run, or local
  behavior from a hosted canary or rendered chatbot proof.
- **Real user use.** No dated evidence yet of an external user installing and
  using the bundle.
