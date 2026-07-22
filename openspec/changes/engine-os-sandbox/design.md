# Design: universe engine OS sandbox

## Objective

Put a fixed, fail-closed Bubblewrap boundary underneath every local CLI subprocess used by the universe intelligence, while retaining the exploit-tested CLI tool policy as defense in depth.

## Audited invocation graph

`tinyassets.universe_intelligence` contains exactly two engine calls:

1. `converse()` reply turn at `call_provider(...)`.
2. `extract_learning()` grounded-learning turn at `call_provider(...)`.

Both calls pass `_sandboxed_config(ctx)`. `tinyassets.providers.call` forwards that config to `ProviderRouter.call_sync`; every router path (`call`, policy routing, and ensemble routing) passes `universe_context.universe_dir` and the same config into `provider.complete(...)`.

Subprocess-backed provider call sites audited:

- `ClaudeProvider.complete`: `asyncio.create_subprocess_exec` plus the Windows `.cmd` shell branch.
- `ClaudeProvider.complete_json`: the same two launch branches.
- `CodexProvider.complete`: already rejects every `sandbox_workspace=True` call before process creation because Codex cannot enforce the existing tool policy.
- Other registered providers are in-process HTTP clients and do not launch a host CLI process.

The wrapper therefore belongs in the Claude provider immediately after command/tool flags and provider environment are assembled, before either `create_subprocess_*` call. It is activated by the existing `ModelConfig.sandbox_workspace` invariant, so it covers both current universe turns, `complete_json`, policy/fallback router paths, and future sandboxed engine calls. `_sandboxed_config` also performs the Linux availability check before routing so an unavailable sandbox refuses the entire engine turn instead of allowing the router to try a downgraded local path.

## Fixed mount and namespace policy

On Linux the wrapper launches:

- Bubblewrap executable returned by `shutil.which("bwrap")`, but only after `providers.base.get_sandbox_status()` reports the cached two-stage functional probe healthy.
- `--die-with-parent`, `--new-session`, `--unshare-all`, `--share-net`, and `--cap-drop ALL`. PID, IPC, UTS, cgroup, and user/mount namespaces are isolated; the host network namespace is deliberately shared because the approved capability is `WebFetch`.
- Fresh `/proc`, minimal `/dev`, tmpfs `/tmp`, and tmpfs `/home` with `HOME=/home/tinyassets` and `CLAUDE_CONFIG_DIR=/home/tinyassets/.claude`.
- Read-only runtime binds: `/usr` (Node, CA tooling, `/usr/local/bin/claude`), `/opt/claude-code-install` (the pinned production CLI), `/bin`, `/lib`, and `/lib64` when present.
- Read-only network/runtime files only: CA certificates, `resolv.conf`, `hosts`, `nsswitch.conf`, `passwd`, `group`, and `localtime` when present.
- One read-write bind: the resolved universe directory at `/workspace`, followed by `--chdir /workspace`.
- A sanitized environment containing only the provider authentication value required for this turn plus PATH, locale, proxy, and certificate settings. Host `HOME`, `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, connector configuration, GitHub credentials, and unrelated process secrets are removed.

Not bound: `/app` (the deployed repo), `TINYASSETS_REPO_ROOT`, the data root, the host root filesystem, host home directories, `~/.codex`, `~/.claude`, SSH/Git/GitHub config, MCP connector config, `/etc/tinyassets/env`, or any vault/credential path. A sandboxed engine that only has file-backed Claude auth therefore refuses; draft rollout requires an environment-backed per-universe OAuth token or API key from the credential-vault lane. This is intentional: mounting a live credential directory would let a future unenumerated read tool recover it.

The child necessarily receives its own provider token/API key in its environment so the Claude client can authenticate. Bubblewrap cannot hide a process's own environment from that process; the existing denylist remains load-bearing against shell/process tools, and credential brokerage or Anthropic-only egress would be a separate hardening layer. This change makes no claim to solve in-process token exfiltration.

## Failure semantics

- Linux + unhealthy/missing functional probe: raise `SandboxUnavailableError` before router invocation; no provider subprocess is created.
- Linux + probe/launch drift: the wrapper refuses before spawn if the bwrap executable disappears, and existing stderr detection remains active for launch failures.
- Codex assigned to a sandboxed turn: preserve its current `ProviderError` refusal.
- Non-Linux: preserve the current cwd/tool-flag confinement for development and emit a warning that OS isolation is unavailable. This is the only downgrade and is platform-explicit; Linux never has a bypass flag.

## Alternatives rejected

- Wrapping only `converse()`: misses `extract_learning`, `complete_json`, and future sandboxed engine calls.
- Replacing the denylist with Bubblewrap: discards a live exploit-tested control and exposes the universe workspace and auth environment to known tools.
- `--ro-bind / /`: makes the host filesystem readable and fails the core boundary even if it is not writable.
- Binding `~/.claude` read-only: a new read tool could steal subscription credentials; it also violates per-universe custody.
- Network namespace with no egress: breaks the host-approved `WebFetch` capability and the provider API itself.
- Reusing the distributed-execution `SandboxRunner`: that protocol isolates untrusted jobs and opaque workspaces; the universe engine is a provider subprocess with a different auth/network contract. It supplies precedent for fail-closed attestation, not the launch implementation.

## Verification

- Unit tests assert exact namespace/mount/environment construction and prove no host/repo/credential path is included.
- A provider test asserts both `complete` and `complete_json` launch the wrapped command while retaining the CLI denylist flags.
- An unavailable-probe test asserts `_sandboxed_config` refuses before `call_provider` can run.
- A Linux integration test creates a secret outside the universe directory, runs a command through the real wrapper, and asserts the secret is unreadable while a file inside `/workspace` is writable.
- Mutation proof: reverting the wrapper/precheck commit must make the focused tests fail; this evidence is recorded in the PR.

## Not doing

- No denylist removal or weakening.
- No WebFetch SSRF policy.
- No distributed user-code runner/backend work.
- No credential-vault or router edits while R2-1 owns those files.
- No deploy, merge, or live acceptance claim.
