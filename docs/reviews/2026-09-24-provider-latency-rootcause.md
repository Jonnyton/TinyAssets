# Parallel-probe latency and probe idle timeouts: root cause

2026-09-24, Claude (Opus 5.5) interactive lane, branch
`claude/provider-latency-rootcause`, base `1e6f6eba`. All production reads
were read-only (`python scripts/droplet.py ssh -- 'docker exec -i
tinyassets-daemon python -' < query.py`), SQLite opened `mode=ro`, limited to
the founder universe `u-01kxm1vszd8hwp7em418asq8h9` and the app agent's two
probe Branches (`279c1b5f5bf0` parallel, `5b7880458f0c` sequential). No prompt
text, response text, tool input content or credential was printed. Tool
*names*, path *prefixes*, first shell words, timings and token counts only.

## Verdict

**Issue #3 (parallel probe 37-280s, two 300s node timeouts): cause
established.** The extra time goes to the model doing *agentic work nobody
asked for*: exploring the platform's source tree. It is not queue wait, sync
pool slots, the concurrent chat turn, rate limits, overload or host pressure.

A workflow prompt node launched `claude -p` with a bare `ModelConfig`: no cwd
pin, no tool policy. The CLI therefore started in the daemon's working
directory, `/app` (the TinyAssets source), with its default builtins. In about
half the runs the model answered an `angle_a`/`angle_b` "short prompt" by
running `find`/`grep` over `/app/tinyassets`, reading `PLAN.md`, starting
`Explore` subagents and trying `python`. Those runs produce 10-30x the
output tokens at unchanged generation speed.

**Issue #4 (sequential `provider_idle_timeout` on `gather`): the only probe
failure has an existing explanation. The `tool_result` / 30067 ms record is not
from `gather`.** The one `gather` failure (`6ffec5e973734074`, 2026-09-21
06:52 UTC) predates the in-flight-tool allowance (#3905, merged 19:44 UTC that
day). `gather` makes 2-4 `WebSearch` calls on every run, so a slow search then
read as silence. There have been 0 `gather` failures in about 50 runs since.
The 30067 ms post-tool-result record (2026-09-24 02:11:31 UTC) comes from the
**served chat turn** (`served turn failed universe=...`), as do all five claude
idle-timeout records in Vector since 2026-09-20. Its cause is **not
established**, and the missing telemetry is added here (see below).

## Evidence

### 1. Time tracks output tokens and API turns, not waiting

Ledger join (`.runs.db` `run_events` x `.tinyassets.db`
`provider_invocation_reservations` via `provider_work_receipts.work_item_id`),
all 34 parallel runs since 2026-09-21:

| run | total | angle nodes (s, uncached input tokens, output tokens) |
|---|---|---|
| 86ea4b8d (clean) | 44.7 s | 13.0 s in=3 out=631; 16.8 s in=3 out=840 |
| bccd6f31 | 38.7 s | 9.7 s in=3 out=285; 17.8 s in=3 out=687 |
| 0bc15721 | 280.9 s | 223.8 s in=19 out=10005; 100.5 s in=13 out=5247 |
| dab4850f | 240.2 s | 188.9 s in=14 out=5637; 164.1 s in=15 out=8922 |
| 7db04431 (fail) | 300.2 s | 283.6 s in=35 out=16193; other timed out |
| 37361392 (fail) | 306.7 s | 300.1 s timeout; 121.3 s in=15 out=6743 |

Every fast angle has `in=3` (one API request). Every slow angle has `in` from
7 to 35, meaning several requests, which in `claude -p` means tool use. Slow
angles output 2.2K-16K tokens against 0.3-1.4K for fast ones. Generation
speed is the same in both: 44-60 tok/s slow (10005/223.8 = 45, 16193/283.6 =
57), 48-50 tok/s fast. That rules out throttling, overload and CPU/memory
starvation as the variable. The reservation `created_at` matches node start to
within 0.2 s in every run, so there is no provider queue or sync-pool wait.
The droplet has 4 vCPU and 8 GB, with memory PSI `full` ~0 and the daemon at
567 MiB of 4 GiB (read 18:46 UTC). The one host fact that could have mattered
is excluded by the constant token rate.

### 2. What the extra requests did

Claude CLI session transcripts for this universe
(`.runtime/provider-child/claude-code/auth-empty/claude/projects/`) were read
as metadata only: event timestamps, tool **names** and usage numbers. Workflow
node sessions live under project `-app`, meaning cwd `/app` (1619 sessions).
Served chat turns live under `-data-u-01kxm...` (281 sessions). Joining sessions
to node start times (±4 s):

- Every slow angle node coincides with sessions such as `{Bash: 14, Read: 15}`,
  `{Bash: 7, Read: 14}` (0bc15721), `{Bash: 12, Read: 8, Agent: 1}`
  (dab4850f) and `{Bash: 24, Read: 11, Write: 2}` (37361392, the 300 s
  timeout).
- Fast angle nodes have no tool sessions.
- `gather` is always `{Skill: 1, ToolSearch: 1, WebSearch: 2-4}`, 22-35 s.
- One slow `gather` (f538d124, 164 s) added an `Agent` subagent, which
  spent 106 s between `tool_use:Agent` and its result.

Across all `-app` sessions since 2026-09-21:

- Read path prefixes: `/app/tinyassets` 171, `/app/PLAN.md` 25,
  `/app/domains` 16, `/app/fantasy_daemon` 14, own-universe CLI temp 13.
- `Bash` first words: `find` 141, `grep` 86, `ls` 14, `python`/`python3`
  11 (all denied), `cat` 6.
- Subagents: `Explore` ×5.
- Two `Bash` commands listed the data root `/data`, which is every
  universe's directory. No other universe's path was read in this window.

Transcripts are truncated because the reader kills the CLI right after the
terminal `result`, so these counts are lower bounds.

### 3. Why the chat turn goes quiet after a tool (cause NOT established)

All five `provider_idle_timeout` records since 2026-09-20 are served chat turns:

- 09-21 22:25:31
- 09-22 08:34:06
- 09-23 04:43:50
- 09-24 00:46:08
- 09-24 02:11:31 (`tool_phase=tool_result`, `last_progress_age_ms=30067`)

Three of them landed within 6-33 s of a slow parallel probe finishing or
timing out (abc24482, 37361392, dab4850f). While waiting, the chat turn polls
`read_graph`: 53 and 56 calls in one turn, 128-151 assistant messages and
40-94K output tokens. A slow probe therefore also makes the chat context much
longer.

The **inference**, not proven: after a tool result, the model's next response
takes more than 30 s to start on that long context. Transcript gaps of 25-89 s
between `tool_result` and the next `thinking` block are consistent with it.
Transcript timestamps mark finished blocks, not stream events, so they cannot
measure protocol silence.

**Missing telemetry, added in this PR:** a turn that goes quiet for most of the
idle bound and then *recovers* left no trace. The claude reader now records:

- `max_silence_ms`: the longest gap between protocol events.
- `max_silence_after`: the event kind before that gap, for example
  `tool_result`.
- `tool_uses`: distinct native tool calls.

These are on every successful `ProviderResponse`. A gap of at least half the
idle bound logs one allowlisted line:

```
claude stream near-idle: max_silence_ms=… after=tool_result idle_s=30 tool_uses=… elapsed_ms=…
```

Workflow nodes' `ran` events now also carry `provider_timing`, which includes
latency, TTFT, input/output tokens, `tool_uses` and max silence. Before this,
`provider_calls` recorded `latency_ms: null`, which is why this diagnosis
needed transcript forensics.

## Fix (smallest correct)

Both workflow launch sites mark the call with the new provider-agnostic
`ModelConfig.workflow_node`. The sites are the foreground run provider
`_call_once` and the background served provider launch, and the mark is added
after the credential snapshot is attached. Each provider applies its own
confinement from the mark. The claude adapter's `_sandbox_cli_args` applies
`_confine_workflow_node`, which sets:

- `sandbox_workspace=True`. The CLI cwd becomes the owner's universe dir and
  `--setting-sources project` is added. The served universe turn already runs
  this way.
- The existing `disallowed_tools`, plus `HOST_REACH_TOOLS`:
  - shell: `Bash`, `BashOutput`, `KillShell`, `Monitor`
  - filesystem: `Read`, `Write`, `Edit`, `MultiEdit`, `NotebookEdit`,
    `NotebookRead`, `Glob`, `Grep`, `LS`

`HOST_REACH_TOOLS` is now the one definition. The universe engine's denylist
starts from it instead of repeating the names.

What is **not** changed:

- No timeout, cap, retry or replay.
- No graph-shape limit.
- Web tools (`WebSearch`/`WebFetch`), subagents, skills and every other
  owner-level capability stay as they were. `gather` keeps searching.
- Codex does not act on the mark yet. Its equivalent is the OS jail, filed as
  [a concern](../concerns/2026-09-24-codex-workflow-nodes-run-in-host-cwd.md).
  The mark keeps the call sites vendor-neutral, as
  `scripts/check_channel_agnostic.py` requires.

Why this is the platform's call and not the owner's: the claude CLI has no OS
jail here. Its filesystem and shell builtins read whatever the daemon can:

- the platform source
- every universe under `/data`
- the credential snapshots beside them

That fails the cross-user floor test, so it is not a leash on the owner. The
node's own model contract already says an ordinary prompt node is a text
interaction (`needs_tools=False`). Tools are declared through `tools_allowed:
["universe_self"]`, and that path already runs sandboxed.

Known side effect: the CLI sometimes saves a large tool result to its own temp
directory and asks the model to `Read` it. That read is now denied, and the
model continues from the truncated preview. This happened 13 times in 3 days,
and 8 of those reads had already errored.

Unverified until live: that CLI 2.1.183 applies `--disallowedTools` inside
`Agent` subagents. The deny rules are session-wide in the CLI's permission
context, but this has not been observed.

## Tests (Windows, Python 3.14.3, repo venv, `--basetemp C:/Users/Jonathan/AppData/Local/Temp/ta-pt-lat`)

New tests. All 9 were red on the unfixed sources: the six changed source files
were swapped to `HEAD` and the new tests run. The 7 existing sandbox tests
stayed green.

- `tests/test_run_provider_session.py::test_foreground_claude_node_runs_in_its_universe_without_host_tools`
  runs a real foreground run through `api_runs._action_run_branch` with codex
  and claude nodes. It checks the captured `ModelConfig`, then asks
  `_sandbox_cli_args` for the argv and cwd.
- `tests/test_background_served_provider.py::test_background_node_call_is_marked_as_a_workflow_node[claude-code|codex]`
- `tests/test_provider_sandbox.py` (2): argv/cwd for a marked call, and
  fail-closed when there is no universe.
- `tests/test_provider_latency_telemetry.py` (4): the real `_read_stream`
  silence and tool count, the near-idle log (and its absence), the allowlist,
  and the real prompt-node `ran` event.

Neighbouring suites: 496 passed, 4 skipped. The skips are 3 symlink-capability
tests and 1 bwrap Linux-only test. Suites covered: provider sandbox, run
provider session, background served provider, stream-and-classify, compaction
liveness, relay prompts, engine MCP server, held diagnostics, direct-run
preferences, graph compiler, universe intelligence.

Full suite, `-n 8`, with `tests/test_wiki_alias_corner_cases.py` ignored
because its module-level `_case_probe.tmp` races across xdist workers during
collection: 141 failed, 22635 passed, 468 skipped. All 139 failures from the
first branch run were rerun against the unfixed sources (the six source files
set to `HEAD`) and set-compared:

- 137 failed at base as well: deploy/installer/backup shell scripts,
  workspace resolver, MCP instruction surfaces, and others.
- The remaining 2 were the `check_channel_agnostic` ratchet. It counted a new
  vendor-named branch at the call sites, so the fix was reshaped into the
  provider-agnostic `workflow_node` mark.

The final run added 4 differences from the base set:

- 3 pass in isolation (env marker, onboarding connect, packaged scoped-reset
  sources). The disk was full during that run.
- 1 encoded "the ordinary session's config passes through unchanged".
  `tests/test_shared_background_self.py` now expects the `workflow_node`
  mark, which is the intended change.

A local Windows run is not an oracle; Linux CI is authoritative.

## Live acceptance (after deploy; not claimed here)

1. `python scripts/deployed_sha.py --assert-contains <merge sha>`.
2. The app agent's ordinary checklist, one send and no replay. Parallel probe
   angles should all show `provider_timing.tool_uses` 0 (or only denied
   attempts), `input_tokens` 3 and roughly 10-25 s. The whole probe should
   take about 35-60 s across repeated runs, with no 300 s timeout. `gather`
   still completes with its searches.
3. New `-app` transcript sessions stop appearing for this universe. Node
   sessions appear under `-data-u-…` with no `Bash`/`Read` calls.
4. Watch Vector for `claude stream near-idle`. A served turn with
   `after=tool_result` and a gap of 15-30 s confirms the post-tool TTFT
   inference; its absence together with a new failure refutes it.
5. Owed: the Codex cross-family review (postponed, ChatGPT rate-limited) and
   an `openspec/specs/provider-routing` as-built requirement for node
   confinement, synced after the live proof.
