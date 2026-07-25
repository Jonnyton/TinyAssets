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
- **Provider-free.** Every packaging probe strips provider credentials from
  its environment and calls no tool — enumeration only. A green packaging
  gate can never depend on maintainer provider quota.

## Observed local auth posture

The bundle configures no WorkOS/OAuth boundary and the wrapper introduces no
auth environment. An uncredentialed stdio client completes `initialize` and
enumerates the catalog; requests then run as the runtime's anonymous local
actor. The product's boundary is the local OS process plus the user-selected
data directory — nothing else.

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
  provider-backed behavior is unproven by this record.
- **Actor-dependent behavior.** Because the local actor is anonymous with no
  founder identity, permission-gated, visibility-gated, ownership-gated, and
  founder-grant behavior is unproven locally and may legitimately differ from
  the hosted product. Do not infer hosted behavior from a local run, or local
  behavior from a hosted canary or rendered chatbot proof.
- **Real user use.** No dated evidence yet of an external user installing and
  using the bundle.
