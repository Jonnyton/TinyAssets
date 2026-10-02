---
severity: P2
title: Universe-file readers outside the turn path
filed: '2026-09-24'
summary: harness S1 routes every turn-path read through `universe_files` and keeps the agent's write set small; ~20 other modules still read universe files raw, safe only while those paths stay agent read-only
---

# Universe-file readers outside the served turn path (harness S1)

**Found:** 2026-09-24, harness S1 review round 2 (PR #3972). **Severity:** P2
today (none of these files is agent-writable), P0 the moment a slice widens
what the agent may write. **Owner:** whoever widens the tool jail's
read-write set.

## Context

Since S1 the universe agent writes its own folder, so a file under a universe
dir is untrusted input to any daemon code that reads it. Three review rounds
found the same class (a raw `read_text`/`yaml.safe_load` with no bound and no
no-follow). The fix has two halves:

1. **What the agent can write is small and explicit.** The tool jail mounts the
   universe root read-only and binds read-write only
   `universe_tools.AGENT_BRAIN_FILES` + `AGENT_HARNESS_DIRS`; every hidden root
   entry (credential vault, `.runtime`, consent/usage/receipt DBs) is masked.
   `tests/test_universe_tools.py::test_agent_owned_paths_are_pinned` pins that
   set.
2. **Every daemon read on the turn path goes through `universe_files`**
   (link-free, bounded, alias-free YAML), enforced by
   `tests/test_universe_file_reads_are_bounded.py` over `TURN_PATH`.

## The rest of the grep (2026-09-24)

`grep -l 'universe_dir|udir'` crossed with `read_text|read_bytes|open(|yaml.*load`
over `tinyassets/`. None of these reads a path in the agent's read-write set,
so none is reachable by an agent write today. Each still reads raw.

| Module | What it reads under a universe | Agent-writable? |
|---|---|---|
| `api/universe.py`, `api/runs.py`, `api/branches.py`, `api/pending_requests.py`, `api/helpers.py` (`_read_json`, `_read_platform_text`) | premise, `activity.log`, `work_targets.json`, `.runtime_status.json`, `.pause`, request docs | No (read-only or masked) |

**Resolved for `wiki/` (harness W, 2026-10-01).** `wiki/` is now agent-writable.
`api/wiki.py`, `api/helpers.py`, `effectors/wiki_write_back.py` and
`wiki/okf_export.py` are in `TURN_PATH`: a wiki page reads link-free and bounded
through `universe_files`, and an oversized or linked page raises instead of
reading as empty. The trusted write-back markers moved from `wiki/` to the
universe root.
| `api/status.py` `_platform_has_work` | EVERY universe's `work_targets.json`, unbounded `json.loads` | No — but a cross-user amplifier if it ever becomes writable |
| `work_targets.py`, `mcp_server.py` | `work_targets.json`, legacy status/progress/chapters | No |
| `credential_vault.py`, `providers/base.py`, `providers/codex_provider.py`, `providers/definition.py`, `provider_assignment.py`, `storage/outbound_connections.py` | `.credential-vault.json`, `.credentials/`, `.runtime/`, admission lock | No (hidden root entries, masked) |
| `onboarding/__init__.py` | package assets | Not a universe path |
| `graph_compiler.py` | the string `"open("` in a denylist | Not a read |

## Resolution rule

Before adding ANY path to `AGENT_BRAIN_FILES` / `AGENT_HARNESS_DIRS` (e.g. S2's
`AGENTS.md`, S4's `workflows/*.yaml` as authority, a writable `wiki/`), route
every reader of that path through `tinyassets.universe_files` and add its module
to `TURN_PATH` in the enforcement test, in the same change. Delete this file
when every row above reads through `universe_files` or the path is gone.
