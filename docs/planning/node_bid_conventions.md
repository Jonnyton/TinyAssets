# Node Bid Conventions

Phase G public-facing reference.

## Directory layout

```
<repo_root>/
  bids/
    <node_bid_id>.yaml
    <node_bid_id>.yaml.claimed_by_<daemon_id>   # post-claim rename
    .gitkeep
  bid_outputs/
    <node_bid_id>/
      output.json
  settlements/
    <node_bid_id>__<daemon_id>.yaml
```

Bids live at repo root, alongside `goal_pool/`. Resolution of `repo_root` uses the same contract as Phase F (`TINYASSETS_REPO_ROOT` env → git-detect upward → `RuntimeError`).

## YAML shape

See `bids/README.md` for the user-facing post format.

## Sandbox model

Three-layer defense in `tinyassets/executors/node_bid.py`:

1. **Registration + approval.** `node_def_id` must resolve in the local node registry with `approved=True`. Unknown or unapproved → `CompilerError`.
2. **Source-pattern rejection.** The approved node's `source_code` must NOT contain any pattern in `_BID_DANGEROUS_PATTERNS` (from `tinyassets/graph_compiler.py`): `os.system`, `subprocess`, `eval(`, `exec(`, `__import__`, `compile(`, `open(`, `importlib`, `pickle`, `marshal`. This is a strict superset of the wrapper-node list (`_DANGEROUS_PATTERNS`). Network patterns (urllib, requests, socket, http.client) are intentionally NOT rejected — approved nodes may legitimately call LLM APIs.
3. **Inputs flat-dict re-validation.** Producer-side already filtered; executor re-validates as defense-in-depth.

Also: `required_llm_type` hard filter, `timeout_seconds` wrapping, `evidence_url` shape validation (http/https/file schemes only).

## Bid term cap

Dispatcher scoring includes `bid_term = min(bid_coefficient * bid, bid_term_cap)`. Default `bid_term_cap=30.0`. The cap preserves tier hierarchy: even a max-bid paid_bid task (tier=50 + cap=30 = 80) cannot outscore a zero-bid host_request (tier=100). Configurable per host via `dispatcher_config.yaml`.

## Claim atomicity

See `bids/README.md`. Git-rename + push with revert on push-fail. Local-only installs skip the pull/push steps (single-daemon, no race).

## Outcome-gate coupling (opt-in Sybil-resistance stub)

A bid with non-empty `goal_id` triggers a synchronous `gates claim` call after successful execution, using `result.evidence_url` as proof. Failed bids never claim gates. This ties bid completion to the gates ladder: a daemon can't sybil its way to gate-claims without actually completing approved-node work.

## Settlements ledger

Every completed bid writes a `settlements/<bid>__<daemon>.yaml`:

```yaml
schema_version: "1"
bid_id: nb_...
daemon_id: daemon-uni-a
requester_id: alice
bid_amount: 10.0
evidence_url: file:///…
completed_at: 2026-04-14T20:01:00+00:00
outcome_status: succeeded
settled: false
```

Records are **immutable in v1**. A future token-launch phase reads this ledger, mints tokens, and either emits v2 records or flips `settled: true` — migration choice deferred. The v1 audit trail is preserved byte-for-byte regardless.

## Flag gating

`TINYASSETS_PAID_MARKET=off` by default. Import-time registration; flipping at runtime requires a TinyAssets daemon restart.
