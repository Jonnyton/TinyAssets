# Incident audit — the uptime canary was falsely red for 6 days and paged 109 times

**Date:** 2026-07-22
**Author:** claude-code (lane `docs/audit-canary-false-red-0722`)
**Class:** monitor contract drift → false P0 → alarm fatigue
**Severity:** P0 surface (Forever Rule: 24/7 uptime), **zero user impact**
**Status of remediation:** nothing fixed. Three lanes proposed, none landed (§8).

All evidence in this document was gathered or reproduced on **2026-07-22** unless
otherwise stamped. Every factual claim carries a sha, `file:line`, CI run id, or
command.

---

## 1. Summary

The project's highest-priority monitored surface reported a **P0 public MCP
outage continuously from 2026-07-15T21:31:53Z to 2026-07-22T01:11:35Z** — 104
consecutive failed runs across 6.15 days, with not one green run in the window.

There was no outage. The live service was behaving **correctly** for all 104 of
those runs. The canary was asserting a server contract that the server had
stopped honoring 37 minutes before the first red.

The alarm channel absorbed the entire event silently: because the sink appends
to an already-open issue rather than opening a new one, all 104 false reds
collapsed into issue **#1461**, which now carries **109 comments** and still
reports `page_eligible=true`.

This is a **recurrence**. The same class was diagnosed and fixed eight days
earlier in `6f8cebc7` / PR #1449 — and `git blame` shows the lines that are now
stale are *the very lines that fix wrote* (§5).

---

## 2. Timeline

| Time (UTC) | Event | Evidence |
|---|---|---|
| 2026-07-14 05:43:10 | Prior instance of this class opens alarm issue **#1447** | `gh issue view 1447` |
| 2026-07-14 23:43:38 | Prior instance fixed by `6f8cebc7` — "align uptime canaries with #1441 anonymous-write gate (stops false P0 alarm) (#1449)"; #1447 closed 23:43:39 | `git show -s 6f8cebc7`; `gh issue view 1447` |
| 2026-07-15 20:38:50 | **Last green canary run** | run `29449080825` |
| 2026-07-15 20:54:19 | `972d0cc3` — "feat(auth): anonymous write tools/call answers 401 WWW-Authenticate pre-dispatch" moves the server contract again. Canary not updated. | `git show -s --format='%ci' 972d0cc3` (13:54:19 -0700) |
| 2026-07-15 21:31:53 | **First red run.** Signature `wiki=6`. | run `29452256324` |
| 2026-07-15 21:35:48 | Alarm sink opens issue **#1461** — "P0 Public MCP outage — 2026-07-15T21:35:48.562Z" | `gh issue view 1461` |
| 2026-07-15 → 2026-07-22 | 104 consecutive failures, identical signature; 108 further comments appended to #1461 | `gh run list --workflow=uptime-canary.yml` |
| 2026-07-22 01:11:35 | Most recent red at time of writing | run `29882421314` |

The 37-minute gap between the last green run and the deploy of `972d0cc3`, and
the 16-minute gap between that commit and the first red, make the causal link
tight enough to state without hedging.

> **Correction to the originating brief.** The brief described this as "60 of
> the last 60 runs, back to 2026-07-18T12:09:10Z" — 4 days. That was an artifact
> of a `--limit 60` fetch window, not the real extent. Fetching 200 runs shows
> the last success was **2026-07-15T20:38:50Z** and the streak is **104 runs /
> 6.15 days**. The incident is ~50% longer and ~73% larger than first reported.
> Command: `gh run list --workflow=uptime-canary.yml --limit 200 --json conclusion,createdAt`.

---

## 3. What actually broke

### 3.1 It was never an outage

Run `29878986733` (2026-07-22T00:02:03Z) combined line:

```
=== combined: handshake=0 tool=0 activity=0 revert=0 wiki=6 worst=6 ===
```

Four of five probes green. Only the wiki probe red. The **first** red run,
`29452256324` (2026-07-15T21:32:04Z), carries the byte-identical signature —
so the whole 104-run streak is one cause, from the first alarm onward.

### 3.2 The live cause, reproduced

Reproduced against production on 2026-07-22:

```python
import scripts.wiki_canary as wc
wc.run_canary('https://tinyassets.io/mcp', timeout=30, verbose=True)
# → ToolCanaryError code=6
# → "HTTP 401 on tools/call: Unauthorized"
```

That 401 is the **correct** current behaviour. `972d0cc3` made pure-write MCP
handles answer HTTP 401 + `WWW-Authenticate` *pre-dispatch*, so that MCP clients
launch OAuth — tool-JSON rejections never prompt sign-in.
`tinyassets/universe_server.py:155-159` documents the contract; `write_page` is
registered with `anonymous_write_challenge=True` at
`tinyassets/universe_server.py:911` (alongside `write_graph`:632,
`run_graph`:674, `converse`:979).

The canary still asserts the *older* in-band envelope — `status=rejected` +
`auth_required=true` — at `scripts/wiki_canary.py:232-237`.

### 3.3 A refinement worth recording

The canary does not actually reach that envelope assertion in production. The
`post()` helper raises on the HTTP 401 first, at `step_code=6`
(`scripts/wiki_canary.py:199-205`). The envelope-checking code at
`scripts/wiki_canary.py:223-237` is now **unreachable against the live server**.

This matters for the fix: realigning the canary is not a matter of editing the
envelope assertion. The probe must first stop treating a 401 on `tools/call` as
an error at the transport layer, because for a pure-write handle a 401 is now
the success condition.

---

## 4. Why nothing caught it — four independent mechanisms

### 4.1 Drift in a monitor is invisible by construction

A monitor whose expectations are hand-copied from server behaviour will drift
when the server moves. The failure mode is uniquely bad because **drift and
outage are indistinguishable at the alarm**: both present as "the P0 surface is
red." The natural operator response is to investigate production — which is
healthy — rather than to suspect the probe. Six days of red is the cost of that
ambiguity.

### 4.2 The tests validate the mock, not the contract

```
python -m pytest tests/test_wiki_canary.py -q     → 31 passed
python -m pytest tests/test_anonymous_write_challenge.py -q → 16 passed
```

Both green, on 2026-07-22, while the canary is 100% red in production.

`tests/test_wiki_canary.py` builds its fixture in `_wiki_write_rejected_resp()`
(`tests/test_wiki_canary.py:69-80`), which hand-writes
`{"status": "rejected", "auth_required": true, ...}` — a response shape
production **no longer emits**, under a comment that still calls it the
"Post-#1441 happy path."

Meanwhile `tests/test_anonymous_write_challenge.py` pins the *new* 401 contract
and also passes. **Both contracts live in the repo, both are green, and nothing
cross-checks them against each other or against the live server.** The canary
test suite cannot go red for the failure that is actually occurring.

This is the `silent-failure-dispatch-and-tests` pattern recurring in a new
place: a guard that cannot fail is not a guard.

### 4.3 The canary throws away its own diagnostic

The precise mechanism, which is narrower than "it doesn't print":

`.github/workflows/uptime-canary.yml:212-213` invokes the probe as

```bash
python scripts/wiki_canary.py --url "${PROBE_URL}" --timeout 20 --verbose 2>&1
```

with **no `--format gha`**. So `fmt` defaults to `log`. In `run_probe`
(`scripts/wiki_canary.py:295-301`) the `ToolCanaryError` message is routed to
`_append_log(...)` — a file on the ephemeral CI runner, discarded when the job
ends — and `_emit_gha_kv("msg", exc.msg)` fires **only** when `fmt == "gha"`.
The message reaches neither stdout nor `$GITHUB_OUTPUT`.

The workflow faithfully echoes what it captured. The CI log for run
`29878986733` therefore reads:

```
=== wiki canary (https://tinyassets.io/mcp) exit=6 ===
[wiki-canary] handshake OK sid='4543b417cb6e4c97b053b3e5cae117a1'
```

An exit code and a *success* line from the preceding step. The string
`Unauthorized` appears nowhere in the run log. Root-causing this required
importing the module locally and catching the exception by hand — for a P0
alarm that had been firing for six days.

### 4.4 Exit code 6 is overloaded across incompatible severities

`step_code=6` is raised for all of: a transport/network error
(`scripts/wiki_canary.py:199-205`), `write_page returned no result` (:207),
`isError=true` (:211), no text content (:216), non-JSON text (:220-222),
envelope mismatch (:232-237), **and** "anonymous write_page was ACCEPTED — the
anonymous-write gate (#1441) has regressed" (:223-231).

The last of those is a live security regression on the public write surface. It
shares a code with a transient network blip. So the single scariest reading of
exit 6 was also the least legible one, and no operator glancing at `wiki=6`
could tell which had happened.

---

## 5. The recurrence, and why it is the central finding

`6f8cebc7` (2026-07-14, PR #1449) is titled:

> fix(canary): align uptime canaries with #1441 anonymous-write gate (stops false P0 alarm)

Its commit body describes the identical shape:

> The write gate (#1441, deployed 07-14 04:55Z) broke two Layer-1 probes that
> still spoke the pre-gate surface, turning the uptime canary red hourly and
> feeding false P0 REDs to alarm issue #1447

`git blame -L 220,240 scripts/wiki_canary.py` attributes the now-stale envelope
assertion to **`6f8cebc7` itself**. The lines that broke are the lines the
previous fix for this exact class wrote, one day before the server moved again.

Side-by-side:

| | Round 1 | Round 2 |
|---|---|---|
| Server change | #1441 write gate, deployed 2026-07-14 04:55Z | `972d0cc3`, 2026-07-15 20:54Z |
| Alarm issue | #1447 | #1461 |
| Duration | ~18h (05:43 → 23:43 same day) | **6.15 days, ongoing** |
| False-alarm comments | 16 | **109** |

The remediation in round 1 was to **re-copy the new contract into the probe by
hand**. That fix was correct for the instance and did nothing for the class — it
left the probe still hand-mirroring a contract that another commit could move
without any signal. Round 2 arrived 21 hours later and lasted 8× longer.

**The finding is not "the canary is stale." It is that a hand-mirrored contract
between two components, with no shared fixture and no cross-check, will drift
again — and the second drift was worse than the first because the alarm channel
had by then been trained to be ignorable.**

---

## 6. Alarm fatigue — dedup turned a stuck alarm into permanent silence

`.github/workflows/uptime-canary.yml:514-525`:

```js
if (overall === 'red') {
  if (openIssue) {
    await github.rest.issues.createComment({ ..., body: formatBody('RED') });
    console.log(`appended RED to #${openIssue.number}`);
    core.setOutput('page_eligible', 'true');
```

Dedup-by-open-issue is correct for a *burst* — it prevents 104 separate issues.
It is wrong for a *stuck* alarm, because the escalation ladder keeps
`page_eligible=true` while the destination becomes progressively less readable.

One correction to the brief's framing: **#1461 is not a pre-existing unrelated
outage thread that this incident got appended to.** Its title timestamp
(`2026-07-15T21:35:48.562Z`) places it ~4 minutes after this streak's first red
run (21:31:53Z). #1461 *is* this incident's own first false alarm. The dedup
logic then folded its own 108 subsequent false reds into it.

The operational consequence: **a genuine outage arriving today would be comment
#110 on a thread titled "P0 Public MCP outage" that has been continuously wrong
for six days.** The channel is not merely noisy; it has been trained to be
ignored, by a signal that was never true.

*Proposed, not landed:* the ladder should distinguish a repeating **identical
signature** from a fresh failure — e.g. suppress re-paging when the failure
signature is unchanged for N runs, while escalating differently (or opening a
distinct "monitor may be stale" issue) once a single signature persists past a
threshold no real outage plausibly would. This is a design sketch; it has not
been reviewed or implemented.

---

## 7. Silent cascade

"Community loop watch" is red purely downstream. Run `29876503654`
(2026-07-21T23:14:53Z, conclusion `failure`) summarizes:

```json
"summary": "uptime-canary.yml latest run concluded failure"
```

Its five most recent runs are all `failure`. Two red workflows, one cause — a
second surface reporting the same false signal, further diluting the value of a
red dashboard.

*Unverified:* whether any other workflow or probe depends on
`uptime-canary.yml`'s conclusion in the same way. Only `community-loop-watch.yml`
was checked.

---

## 8. Status — fixed / proposed / unverified

Stated plainly, because none of the recommendations in this document are landed.

**FIXED: nothing.** As of 2026-07-22 the canary is still red, the contract is
still hand-mirrored, the diagnostic is still discarded, and #1461 is still open
and accumulating.

**PROPOSED (dispatched, no branch, no PR).** Three remediation lanes were queued
alongside this audit at `output/s2-gate/_queue/dispatched/`:

| Lane brief | Intended branch | Scope |
|---|---|---|
| [`uptime-canary-false-red-p0.md`](../../output/s2-gate/_queue/dispatched/uptime-canary-false-red-p0.md) | `fix/wiki-canary-401-contract` | Realign the probe to the 401 write-gate contract |
| [`canary-swallows-its-own-diagnostic.md`](../../output/s2-gate/_queue/dispatched/canary-swallows-its-own-diagnostic.md) | `fix/canary-error-reporting` | Surface the `ToolCanaryError` message in CI output |
| [`canary-contract-drift-guard.md`](../../output/s2-gate/_queue/dispatched/canary-contract-drift-guard.md) | `test/canary-contract-drift-guard` | Bind the canary mocks to the real contract |

Verified 2026-07-22: `gh pr list --state open` returns **no** PR on any of those
branches, and `git ls-remote --heads origin | grep -i canary` returns **nothing**.
All three lanes were dispatched and produced no artifact. That is itself an
instance of the dispatch-silently-produces-nothing pattern already recorded in
`.agents/activity.log` (`2c1f63cb`, "record four s2-gate lanes that produced no
PR") — worth noting so the remediation is not assumed to be in flight.

**UNVERIFIED:**
- Whether the other Layer-1 probes (`handshake`, `tool`, `activity`, `revert`)
  hand-mirror contracts that could drift the same way. Not audited here.
- Whether the daemon's paused state (run `29878986733`: `[last-activity] FRESH
  (paused/paused): daemon is intentionally paused via .pause signal`) interacts
  with any of this. Noted, not investigated.
- The §6 escalation redesign is a sketch, not a reviewed proposal.

---

## 9. Recommendation for the living files

Per AGENTS.md § "Truth And Freshness", the diagnostic half belongs here and the
stable conclusion belongs in the living files. **This lane deliberately does not
edit `STATUS.md`** — PR #1506 (`claude/status-janitor-0722`) and PR #1507
(`claude/status-release-cron-watch`) are both mid-flight against that file.

Recommended for whoever lands #1506/#1507 to fold in — a Concern row, ≤150 chars:

> **[P1 filed:2026-07-22]** Uptime canary falsely red 104 runs / 6.15d (recurrence of #1449); probe hand-mirrors server 401 contract, tests mock the dead shape. 3 lanes dispatched, 0 PRs.

**Issue #1461 needs triage and closure once the canary is green.** It is flagged
here deliberately and **has not been closed by this lane** — closing it while
the canary is still red would remove the only visible trace of a live P0 surface
being unmonitored. It should be closed as part of, or immediately after, the
`fix/wiki-canary-401-contract` landing, with a note recording that its 109
comments were all false.

---

## 10. Cross-family review

A Codex review of the underlying technical claims was dispatched to
`docs/audits/2026-07-22-uptime-canary-false-red-codex-review.md`. **As of this
writing that review had not returned**, so this audit reflects only
independently-verified first-party evidence — every claim above was reproduced
against the repo, the CI history, or the live service by this lane, not taken
from the originating brief.

Two of the brief's claims were **corrected** by that verification (streak extent,
§2; the nature of #1461, §6) and one was **refined** (the failure raises at the
transport layer, not the envelope assertion, §3.3). When the Codex verdict
lands, its `approve` / `adapt` / `reject` result should be appended here.

---

## Appendix — commands to reproduce

```bash
# Extent of the red streak (the --limit 60 default understates it)
gh run list --workflow=uptime-canary.yml --limit 200 --json conclusion,createdAt,databaseId

# The signature — first red and latest red are identical
gh run view 29452256324 --log | grep "combined:"
gh run view 29878986733 --log | grep "combined:"

# Live reproduction
python -c "import scripts.wiki_canary as wc; wc.run_canary('https://tinyassets.io/mcp', timeout=30, verbose=True)"

# Green tests, red production
python -m pytest tests/test_wiki_canary.py tests/test_anonymous_write_challenge.py -q

# The recurrence
git blame -L 220,240 scripts/wiki_canary.py
git show -s 6f8cebc7 972d0cc3

# Remediation status
gh pr list --state open --limit 60 --json number,headRefName | grep -i canary
git ls-remote --heads origin | grep -i canary
```
