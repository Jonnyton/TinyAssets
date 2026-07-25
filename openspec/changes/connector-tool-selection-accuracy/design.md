# Design — connector tool-selection accuracy

## Context

Carries task 6.3 of `reconcile-universe-personification-relay`, the residual of retired task 2.9.
The definition shape was drafted in that change's `implementation-notes.md` §6.3; this change turns
it into requirements plus the instrument they need, against `live-mcp-connector-surface` (which owns
the prompt catalog and the canonical seven-handle set).

Filing it separately was deliberate, not bureaucratic: the metric belongs to the connector surface,
not to persona forkability, and it was outside the relay change's Files boundary.

## Decisions

### D1 — The instrument is a versioned file, and a revision is a new version

A dataset that can be edited in the same change that moves the metric is not an instrument. Version
comes from the filename (`connector_tool_selection_v1.jsonl`), a baseline records the version it was
measured against, and `compare_to_baseline` refuses a cross-version comparison outright rather than
silently comparing incomparable numbers.

Rejected: storing the version inside the file. A field can be edited without the filename changing,
which is exactly the drift the versioning exists to prevent.

### D2 — Integrity rules raise; they never warn

Every dataset defect (a non-canonical label, an uncovered handle, a duplicate prompt, a torn JSON
line, an empty prompt) raises `DatasetError`. A malformed instrument that still produces a number is
worse than no number, because the number reads as evidence.

The torn-line case is the sharp one: skipping an unparseable line would silently shrink the
dataset and *raise* the apparent accuracy. It raises instead, naming the line.

### D3 — Two rates, never pooled

Top-1 accuracy over the whole dataset, and the `converse`-first-on-opening rate over the
`opening: true` subset, are reported separately. `first-contact` depends specifically on `converse`
being chosen on an opening message, and there are few opening prompts relative to the whole set — so
a total opening-turn collapse moves a pooled average by a couple of points and hides.

`tests/test_connector_tool_selection.py::test_opening_regression_is_visible_when_top1_barely_moves`
encodes this concretely: every opening prompt wrong, top-1 still >0.95, opening rate 0.0.

### D4 — Partial runs are refused, not scored

If a recorded run omits prompts, the harness raises rather than reporting a rate over what it has.
Otherwise the cheapest way to pass the gate is to leave out the prompts that failed. Runs carrying
prompts *outside* the dataset are refused for the mirror reason — that silently changes the
instrument.

### D5 — Tolerance lives on the baseline, not in the call

`compare_to_baseline(measurement, baseline)` takes no tolerance argument. If the threshold were a
parameter, a failing run could be rescued at the call site, which is the same class of defect as
gaming a gate by weakening an assertion. The default is 0 pp — no regression — until the
connector-surface owner records a tolerance, and the recommendation is to keep it there while the
handle set is small and the prompts are unambiguous.

### D6 — A non-canonical observed handle scores incorrect *and* is reported

Discarding an unrecognized observation would hide a systematic mis-selection onto a retired or
hallucinated tool. It counts as a miss and the observed value is surfaced, so the failure mode is
diagnosable rather than merely counted.

### D7 — The measurement is human-in-the-loop, and that is not a gap

Handle choice is a property of the host chatbot. It cannot be observed by calling the MCP server
directly — a direct call *is* the selection. So observations come from a rendered `ui-test` session
(AGENTS.md § Quality Gates), and `score_run` refuses any source outside `RENDERED_SOURCES`.

This is the honest boundary of what can be automated here. What the harness does automate is
everything that could turn a bad run into a good-looking number: coverage, integrity, tolerance
handling, and cross-version/cross-surface comparison.

Per-surface rates are never averaged — `claude.ai` and `chatgpt` are different subjects under test,
and a single blended number would let a regression on one hide behind the other.

## Why this is not synced into `openspec/specs/`

`openspec/specs/` is as-built truth. The requirements here are *targets*: no baseline has been
recorded, so the gate is defined but not yet in force. Syncing now would assert a measured,
enforced gate that does not exist.

Note the footgun: `openspec archive` performs the sync. Archiving this change before task 3.1
records a baseline is the same error as running `sync-specs` early — the exact failure mode
`reconcile-universe-personification-relay` was created to prevent.

## Open question for the connector-surface owner

The dataset ships 21 prompts covering all seven handles. Whether that is enough resolution for a
0-pp gate — a single flipped prompt moves top-1 by ~4.8 pp — is the owner's call, and is the
decision recorded in task 2.3. The alternative is a larger v2 dataset before the baseline is taken.
