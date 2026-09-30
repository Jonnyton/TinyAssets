---
severity: P3
title: The file and shell handles still return their refusals as isError false
filed: 2026-09-30
summary: The served read/write/edit/bash handles are exempt from the refusal flag because their text is arbitrary content. As a result, their own refusals (the binding refusal, and "error ..." text) still reach the model as isError false, the same as before the tool-friction PR.
---

# The file and shell handles still return their refusals as `isError: false`

**Found:** gpt-6-astra refute, round 2, of the tool-friction PR (branch
`tool-friction`), 2026-09-30.
**Area:** `tinyassets/engine_mcp_server.py` (`_RAW_CONTENT_TOOLS`,
`RefusalsAreErrors`, `_universe_tool`), `tinyassets/universe_tools.py`.

## What is true now

`RefusalsAreErrors` marks a served refusal `isError: true` by recognising its
JSON shape. The shape test cannot be applied to `read`, `write`, `edit` and
`bash`, because their text is file bytes or command output. A file containing
`{"errors": [...]}` was read successfully and still got flagged (round-1
repro). So those four handles are exempt, and their refusals are unflagged,
the same as on main before this change:

- `_universe_tool` returns `_binding_error()` JSON when the engine is unbound
  or unauthorized. Repro: `_ACTOR_ID = ""`, then call `read` through an MCP
  client, and the result is `isError: false`.
- `universe_tools` returns `error: ...` text for a refused path or a non-zero
  exit. That text cannot be told apart from a file that starts with
  `error: `.

## The fix, when it is worth doing

The handler knows when it refused, so the flag belongs there and not in shape
matching: `_universe_tool` and the `universe_tools` refusal returns should
raise `fastmcp.exceptions.ToolError` with the same text. That changes the
Python return contract that `tests/test_universe_tools.py` (the
`_call_all_four` assertions) and the Linux-only `tests/test_universe_tools_jail.py`
(`startswith("error:")`) assert. Those tests need rewriting, and the jail tests
need `python scripts/linux_oracle.py`. It was left out of the tool-friction PR
because the live evidence was on the `write_graph`/`read_graph`/`run_graph`
handles, and none of it was on these four.
