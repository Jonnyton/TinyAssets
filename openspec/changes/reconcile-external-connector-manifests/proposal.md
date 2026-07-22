## Why

TinyAssets publishes three connector products with deliberately different
transport, authentication, configuration, and review contracts. They share
some handle names, but they are not one interchangeable deployment:

1. the remote `https://tinyassets.io/mcp` WorkOS/OAuth resource server;
2. the local MCPB package, which launches a bundled process over stdio against
   a user-selected data directory and currently supplies no remote-auth config;
3. the narrower remote directory-review surface, whose versioned endpoint and
   submission artifacts advertise five reviewed/redacted handles.

The prior draft and recovered handoff collapsed the first two into a
"live/local" product. Separately, the checked-in MCPB manifest still declares
only hidden legacy `universe` and `extensions` tools even though its bundled
`tinyassets.universe_server` advertises seven canonical handles. Schema
validation can therefore pass while both the metadata and the product model
disagree with what users actually install.

## What Changes

- Specify the remote `/mcp`, local MCPB, and remote directory-review surfaces
  as three product contracts. Shared tool names or schemas SHALL NOT imply
  transport, authentication, configuration, storage, or trust-boundary parity.
- Make the local MCPB manifest declare exactly the seven handles advertised by
  its bundled `universe_server` runtime:
  `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
  `converse`, and `get_status`.
- Add an executable parity check that stages/imports the bundle runtime,
  enumerates its middleware-applied advertised tools, and compares that set
  with the staged MCPB manifest. Packaging validation SHALL fail on drift.
- Preserve the remote MCP Registry and ChatGPT submission packet as the
  intentional five-handle directory-review product backed by
  `directory_server`; reconciliation SHALL NOT expand that surface to seven or
  describe it as a local package.
- Require product-specific acceptance: remote `/mcp` proves Streamable-HTTP and
  the deployed WorkOS/OAuth boundary; local MCPB proves stdio launch, local
  configuration, and its actual auth mode; directory artifacts prove the
  versioned five-handle remote and redaction/review behavior.
- Fold or supersede PR #1522 rather than treating its naming-only rename as the
  content refresh: after the runtime/manifest truth is established, rename the
  recovered Polsia handoff to TinyAssets and replace its stale pre-cutover,
  pre-WorkOS integration guidance with the remote-live seven, local-MCPB
  seven-name catalog, and remote-directory five product split.
- Keep legacy-tool retirement out of this change. It belongs to the dependent
  `retire-legacy-live-mcp-tools` change after manifest migration and external
  consumer evidence.

## Capabilities

### New Capabilities

- `mcp-connector-distribution`: Specify the three connector products, their
  artifact-to-runtime bindings, local MCPB configuration and catalog parity,
  external integration guidance, and non-substitutable acceptance evidence.

### Modified Capabilities

- `live-mcp-connector-surface`: Correct the canonical directory-status wording
  to the as-built exact-five contract: redacted status is served through
  `read_graph(target=status)` and `get_status` is not advertised. No remote
  runtime behavior changes.

## Impact

- Packaging: `packaging/mcpb/manifest.json`, `packaging/mcpb/server.py`,
  `packaging/mcpb/build_bundle.py`, and packaging parity/launch tests.
- Directory metadata: `packaging/registry/server.json`, its deterministic
  generator, and `chatgpt-app-submission.json` remain directory-five and gain
  regression coverage only where existing coverage is insufficient.
- Documentation: the recovered Polsia handoff is renamed and substantively
  refreshed in the implementation lane; PR #1522 overlaps that file and the
  obsolete change being archived, so it must be folded, rebased to the new
  scope, or closed before implementation lands.
- Security: no new auth mechanism is introduced. The specification makes the
  current difference explicit: production remote surfaces use their deployed
  WorkOS/OAuth resource-server boundary, while the MCPB manifest launches stdio
  without supplying `UNIVERSE_SERVER_AUTH` and therefore currently selects the
  runtime's local dev/no-auth provider unless a separately reviewed package
  change adds an identity mechanism.
- Compute: the package and its acceptance suite provide no platform/maintainer
  model, provider account, credential, quota, or compute. Any future model work
  requires requester BYOC or an accepted-market grant; otherwise it remains
  held/setup-required with zero provider invocation.
- Dependency: `retire-legacy-live-mcp-tools` must wait for this reconciliation,
  installed MCPB-host evidence, supported local-host migration evidence, and a
  resolution or explicit redesign of the local identity/authority gap. Remote
  telemetry proves only remote consumer migration.
