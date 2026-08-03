# BUG-045 minimal repro: child-invocation echo probe

Source: dev-partner chat (https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475)
Captured: 2026-05-02

## Existing evidence (parent run 3c76459ed6b64062)
- parent branch: `74219e03dda8`
- parent status: failed
- error: "Sub-branch invocation in node 'invoke_child_lab' produced child_failed"
- child run_id: f7c86a90197b453b
  - child branch: `e019229850f9` (community_change_loop_autoresearch_lab_v1)
  - child status: failed
  - program_intake: ran, baseline_reader: ran
  - error: "expected JSON object response ... no JSON object found"
  - raw response: "[Mock response for baseline_reader]"

## Why a focused probe
`invoke_autoresearch_lab` mixes too many variables: file_bug trigger,
change_loop policy, attachment receipt gate, invoke_branch node, child run
worker ownership, autoresearch prompt quality, strict JSON parsing, output
mapping, parent receipt gate. Good for end-to-end acceptance test, bad as
first characterization probe.

## Decomposition hypothesis
- **BUG-045A** — public authoring / schema support for `invoke_branch` nodes.
  Existing evidence (parent successfully spawned child_run_id) suggests
  this may be partially solved.
- **BUG-045B** — child completion + output mapping + receipt semantics.
  Next probe should target this.

## Probe shape

### `child_invocation_echo_child_v1`
- one node
- deterministic prompt/template or source node (no provider call)
- outputs:
  - `child_status = "ok"`
  - `child_packet = "probe packet <timestamp>"`

### `child_invocation_echo_parent_v1`
- one `invoke_branch` node targeting `child_invocation_echo_child_v1`
- maps `parent.input_text` → `child.input_text`
- maps `child.child_status` → `parent.child_status`
- maps `child.child_packet` → `parent.child_packet`

## Success criteria
```
parent run status: completed
child run_id visible somewhere
child run status: completed
parent.child_status == "ok"
parent.child_packet populated
get_run_output(parent_run_id) returns mapped fields
```

## Failure-mode diagnosis matrix
| Symptom | Diagnosis |
|---------|-----------|
| No child run id | invoke transport / enqueue gap |
| Child completes but parent fails | await/receipt gap |
| Parent completes but mapped fields empty | output mapping gap |
| Parent sees dispatcher_id but no run_id | observability gap (overlaps FEAT-004) |

## Three-layer test sequence
1. **Layer 1**: direct child branch run — prove child outputs are valid in isolation.
2. **Layer 2**: parent invokes child echo branch — prove invoke/await/map without autoresearch complexity.
3. **Layer 3**: parent invokes `community_change_loop_autoresearch_lab_v1` — now any failure belongs to autoresearch quality, JSON contract, provider/mock output, or long-running provider chain.

Once Layer 2 is green, use FEAT-004 / FEAT-005 as the real end-to-end loop
request and observe `change_loop_v1` + `invoke_autoresearch_lab` together.

## Why this matters for 24/7 loop uptime
Without Layer 2 in place, every BUG-045 attempt is a 4-variable diagnosis.
With Layer 2 green, every future invoke_branch failure is a 1-variable diagnosis.
This is substrate-level observability, not a content fix.
