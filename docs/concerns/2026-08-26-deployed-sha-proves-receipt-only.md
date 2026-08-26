# `deployed_sha` proves the receipt, not the running binary

**Filed:** 2026-08-26 | **Verified:** 2026-08-26 | **Severity:** P2
**Found by:** Codex, reviewing the completed harness reset.

> Filed by the harness reset itself rather than migrated from the board.

## The gap

`scripts/deployed_sha.py` is the executable form of Hard Rule 14 — *merged is
not deployed*. It reads `release_state.git_sha` from the live public MCP
surface and asserts production contains a given commit.

But `release_state` is a **JSON file the deploy job writes to the host volume**.
`tinyassets/api/status.py` reads it back and republishes it without comparing it
to the revision actually running. So:

- a manual rollback, or
- an older-image restart that leaves the receipt intact

produces an older server truthfully reporting a newer sha, and
`--assert-contains` returns **0 for code that is not running**. The gate whose
entire purpose is catching "merged but not deployed" can miss "deployed then
un-deployed".

## What is already mitigated

The tool cross-checks `git_sha` against `image_tag` and refuses (exit 2) when
they disagree, so a partial or tampered receipt cannot read as a pass. It also
labels its own output `"proves": "receipt"`. Agreement still does not prove the
running binary — both fields are written together by the same job.

## The fix, and why it was not done here

The public surface exposes no runtime-derived revision. Closing this means
`get_status` reporting the revision of the **running process or image**
(e.g. read at startup from the image label or a build-stamped constant), then
`deployed_sha.py` requiring that value and the receipt to agree.

That is a **product change to `tinyassets/api/status.py`**, not a harness one,
and it lands on an authority-adjacent public surface — so it needs its own
OpenSpec change and Codex review rather than being smuggled into a harness
reset. Recorded here so the gate's limit is tracked rather than buried in a
docstring.

## Closing condition

`get_status` carries a runtime-derived revision, `deployed_sha.py` requires it
to agree with the receipt, and a test proves a stale-receipt/older-image
combination returns non-zero.
