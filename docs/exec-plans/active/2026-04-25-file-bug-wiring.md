# file_bug → bug_investigation forward-trigger wiring

**Status:** spec + helper + tests landed; forward call site UNWIRED (verifier-2 territory).
**Task:** #34 (FRESH-A).
**Goal:** capture the 3-trigger contract for the bug-investigation pipeline and land the testable seam without touching `universe_server.py`.

## Three trigger paths

The canonical bug-investigation branch can be queued via any of three paths; together they form the auto-heal pipeline (filed bug → daemon investigates → patch packet attached as a comment).

| # | Trigger | Owner | State today |
|---|---------|-------|-------------|
| 1 | **Forward** — `_wiki_file_bug` post-write enqueues for the bug just filed. | `universe_server._wiki_file_bug` → `bug_investigation._maybe_enqueue_investigation` | helper landed; call site UNWIRED |
| 2 | **Startup-backfill** — daemon startup scans `pages/bugs/` for bugs without an `## Investigation` section and enqueues each. | daemon startup hook (TBD-located) | unwired; navigator-pass-5 candidate |
| 3 | **30-min safety-net** — scheduler subscription re-scans for un-investigated bugs at a regular cadence. | scheduler (TBD-located) | unwired; navigator-pass-5 candidate |

Forward is the fast path (filing → queued in one MCP turn). Backfill picks up bugs filed before the canonical branch was bound. Safety-net catches anything that slipped through (env was missing, dispatcher was full, helper recovered silently).

## Today's wiring state

- `bug_investigation.enqueue_investigation_request` exists and is tested by `tests/test_bug_investigation_dispatcher.py` (Task #47).
- `bug_investigation._maybe_enqueue_investigation` (Task #34) wraps the env-gate + try/except logic so the call site in `_wiki_file_bug` is a one-liner that cannot break filing.
- `_wiki_file_bug` at `universe_server.py:13102` does NOT call the helper. After `_append_wiki_log` (line ~13221), it returns the filing result directly.
- Backfill + safety-net subscriptions: not located in this audit pass.

## The one-line wiring (verifier-2 to land)

After `_append_wiki_log(...)` and BEFORE the `return json.dumps({...})` in `_wiki_file_bug`, add:

```python
# Forward-trigger investigation pipeline (skipped when env unset; failures swallowed).
from workflow.bug_investigation import _maybe_enqueue_investigation
_maybe_enqueue_investigation(
    bug_id=bug_id,
    frontmatter={
        "title": title,
        "component": component,
        "severity": severity,
        "kind": effective_kind,
        "observed": observed,
        "expected": expected,
        "repro": repro,
        "workaround": workaround,
    },
    base_path=Path(_wiki_pages_dir().parent),
)
```

`base_path` should be the universe directory (the parent of the wiki `pages/` dir under the universe). Helper handles env-unset, dispatcher rejection, and bad input — all return None silently. Filing must return its existing payload regardless of helper outcome.

## Test surface

`tests/test_bug_investigation_wiring.py` covers:

| Class | What it tests |
|-------|---------------|
| `TestEnvGate` | helper returns None when `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID` is unset / empty / whitespace |
| `TestEnqueuesWhenBound` | helper enqueues a `BranchTask` when env is bound; passes `universe_id`; arg `bug_id` overrides any frontmatter `bug_id` |
| `TestGracefulFailure` | helper returns None on dispatcher rejection (RuntimeError), missing `bug_id`, ValueError from inner enqueue, `frontmatter=None` |

The integration test `test_wiki_file_bug_invokes_maybe_enqueue_investigation` is `@pytest.mark.skip` until verifier-2 lands the call site. **Removing the skip** is the gate that flips the wiring from spec to live.

## Fallout / future work

- **Backfill + scheduler:** locate, design, and add tests in a follow-up. Both can reuse `_maybe_enqueue_investigation` (passing every un-investigated bug's frontmatter + base_path).
- **`## Investigation` section append:** when a request is queued, the page should grow an `## Investigation` section noting the dispatcher request id (`format_investigation_comment` already exists in `bug_investigation.py`). This is a separate concern — likely a post-enqueue side-effect from the helper, or a daemon-side ack on claim. Current scope: helper does not touch the page.
- **Cloud daemon redeploy:** even after the call site lands, a stale cloud daemon won't run the canonical branch; that's the host-action row in STATUS.md.

## Why this seam shape

- Helper lives in `bug_investigation.py` (not the test file) so the seam is properly located, not test-fixture-coupled.
- Helper swallows `RuntimeError` / `ValueError` so a misconfigured priorities env or transient dispatcher state can never break filing — filing is the user's primary action.
- Helper reads env at call time (not import time) so test monkeypatching works and the daemon picks up env changes between filings without restart.
- One @skip integration test (not @xfail) keeps the suite clean — fewer "expected failure" outputs to misread, single-line edit to flip on.
