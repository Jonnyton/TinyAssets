# Provider subprocesses can read every user's universe

**Filed:** 2026-09-24, from the PR #3953 root-cause work.
**Severity:** P0, a cross-user floor breach live in production.

Workflow-node provider calls run the model CLI with cwd `/app` (the platform
source) and its shell and filesystem tools enabled. CLI session records show
slow nodes running `find`/`grep` over `/app/tinyassets` and listing `/data`,
which holds every user's universe. Any user's workflow prompt could therefore
cause the model to read another user's data. It is also the cause of the
parallel-probe latency (capability C13): the model explored the source
instead of answering, and took 100–300s.

- PR #3953 confines the Claude adapter for marked workflow-node calls. It sets
  cwd to the owner's universe and denies shell/file tools.
- Codex node calls and any other command-style provider remain exposed until
  a vendor-neutral OS-level jail at the shared spawn point lands. That work is
  in progress; see `2026-09-24-codex-workflow-nodes-run-in-host-cwd.md` on the
  PR #3953 branch.

Acceptance: a jail test proves that a provider subprocess for universe A
cannot read universe B or `/app`, running in `linux-jail-proof`, and the
deploy is verified by `deployed_sha.py`. Delete this file when both hold.
