# Codex build brief — `twitter_post` effector (the thing "PR-173" asks for)

## Why "merge PR-173" had no target
"PR-173" is a **wiki patch_request id** (an internal feature request), **not a GitHub PR**.
- GitHub PR **#173** is an unrelated, already-merged May 2026 PR.
- No open PR/branch implements a twitter effector. The platform's auto-loop tried to
  build it twice and both failed (provider outage `e6ba4b78`, then `propose_changes`
  300s timeout `f296ce41`). **The code was never written.**
- Host approval is already on record ("pr-173 ... approved and needs to merge **once a
  mergeable GitHub PR exists**"). So: **build it → open a PR → merge that.**

## What to build
A new external-write effector `twitter_post`, following the existing PR-122 framework.
**Mirror `workflow/effectors/github_pr.py`; share ZERO adapter code with it** (the
generalization test the filing calls for).

### Files
1. **New `workflow/effectors/twitter_post.py`**
   - `EXTERNAL_WRITE_SINK_TWITTER_POST = "twitter_post"`
   - `def run_twitter_post_effector(...)` — same signature shape as `run_github_pr_effector`.
   - Parse the `external_write_packet` from the run's final state (reuse github_pr's
     `_parse_packet` pattern).
   - **Authority:** `workflow/effectors/authority.py` `resolve_soul_effect_authority(sink="twitter_post", destination=...)`, fail-closed.
   - **Consent:** `effector_consents` with `sink="twitter_post"` (same gate as github_pr).
   - **Idempotency:** atomic reserve on `(idempotency_hint, sink)` via `external_write_receipts`;
     if the packet omits one, derive `idempotency_hint = sha256(source_run_id + sink_handle + text)`.
   - **Dry-run default** via `WORKFLOW_EXTERNAL_WRITE_DRY_RUN` (return a would-post evidence stub, no network).
   - **Real post:** OAuth 1.0a **user-context** `POST https://api.x.com/2/tweets`,
     body `{"text": ...}`; for replies add `{"reply": {"in_reply_to_tweet_id": <id>}}`.
   - **Per-handle credential resolver** (NOT a single PAT): resolve, by sink_handle/destination,
     `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`
     (so multiple accounts are possible; first handle = `@kwisatzh4derach`).
   - **Evidence:** return `{"post_id": <id>, "post_url": "https://x.com/<handle>/status/<id>"}`.

2. **`workflow/effectors/__init__.py`** — export `EXTERNAL_WRITE_SINK_TWITTER_POST` +
   `run_twitter_post_effector`; add both to `__all__` (mirror the github_pr lines).

3. **`workflow/branches.py`** — this is where effects are dispatched after a run (sink → runner).
   Add `twitter_post` → `run_twitter_post_effector` so `external_write_packet{sink:"twitter_post"}`
   is delivered (today an unknown sink yields an unknown-sink evidence error).

4. **Tests** — mirror `test_external_write_effector.py`: dry-run, authority-denied,
   consent-missing, idempotency replay, success evidence shape.

5. **Plugin mirror** — auto-sync if the repo mirrors effectors into a plugin.

### Build to the LIVE canary (so it actually delivers)
`outreach_content_engine_v3` (`d001a70acf2e`) emit node already emits, in `auto` publish_mode:
```json
{
  "sink": "twitter_post",
  "destination": "x:self",
  "payload": {"text": "<str>", "reply_to_tweet_id": "<str|\"\">", "quote_tweet_id": "<str|\"\">"},
  "idempotency_hint": "<sha256 hex>",
  "expected_evidence_keys": ["post_id", "post_url"]
}
```
Naming note: the canary uses `post_id`/`post_url`; the PR-173 filing text says
`tweet_id`/`tweet_url`. Pick one — if you choose `tweet_id`/`tweet_url`, say so and the
canary emit node's `expected_evidence_keys` will be aligned to match.

### Env (host sets these in /etc/workflow/env; effector only reads them)
`TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`
(OAuth 1.0a user-context, Read+Write). `TWITTER_BEARER_TOKEN` is read-only (used by the
separate node-native `x_discover_native` sensor, not by this effector).
