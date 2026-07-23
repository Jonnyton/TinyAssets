# Fail-closed OS sandbox for universe engine turns

## Why

The founder-facing universe intelligence currently relies on Claude CLI tool flags, a pinned cwd, and an enumerated denylist. That mitigation stopped a live P0, but it runs inside the process being confined and will regress when the CLI adds an unenumerated tool. Production `get_status` reported `sandbox_status.bwrap_available=true` on 2026-07-22 around 05:20Z; the existing two-stage probe therefore proved both `bwrap --version` and a functional Bubblewrap launch on the deployed host.

## What Changes

- Wrap every sandboxed Claude engine subprocess in a fixed Bubblewrap policy beneath the existing CLI flags.
- Give the child a minimal runtime filesystem, network access for `WebFetch`, a private temporary home, and one read-write bind containing only the universe's own files.
- Do not mount the repository, host home, Codex/Claude config homes, data root, or credential paths.
- Refuse Linux engine turns before provider routing when the existing functional bwrap probe is unavailable; never downgrade to the CLI-only sandbox.
- Preserve an explicit non-Linux development mode so Windows contributors can run the existing flag-confined path, with a warning that it is not production-equivalent.
- Keep `_ENGINE_ALLOWED_TOOLS`, `_ENGINE_DISALLOWED_TOOLS`, `--setting-sources project`, and Codex's existing refusal unchanged as independent defenses.

## Impact

- Modified capability: `universe-personification-and-relay`.
- Source seam: `tinyassets/sandbox/engine.py`, `tinyassets/providers/claude_provider.py`, and the pre-routing check in `tinyassets/universe_intelligence.py`.
- Tests: focused command-policy, fail-closed, provider-launch, and Linux Bubblewrap escape coverage.
- No deployment or rollout in this change; the PR remains draft and host-gated.
