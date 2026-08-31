# 23 of 37 declared dependencies can ship a major into CI unannounced

**Found** 2026-08-31 while fixing the fastmcp 4.0.0 break (PR #2746). The pin
in that PR fixes *one* package. This file is about the shape.

## What happened once, and can happen again tomorrow

`fastmcp>=3.0` had no upper bound. fastmcp 4.0.0 (with mcp 2.1.1) released,
CI resolved it, `request_ctx` disappeared from `mcp.server.lowlevel.server`,
seven tests failed, and `required-tests` went red on **every open PR at once**
with no commit touching the broken code.

Production was untouched because its container was built earlier and runs
3.4.7. That gap is the whole risk: **CI and production install from the same
unbounded ranges at different times, so they can silently be running different
majors.** The next container rebuild is where that becomes an outage, and the
two modules that import `request_ctx` are on the live MCP path (Hard Rule 11).

## The count

Audited from `pyproject.toml` (`project.dependencies` plus every
`optional-dependencies` table): **23 of 37** entries declare a lower bound and
no upper bound.

They are not equally dangerous, and pinning all 23 would be a worse change than
the problem. Two groups:

**On the live serving path — a bad resolve is an outage:**
`fastapi`, `uvicorn[standard]`, `httpx`, `openai`, `groq`, `google-genai`,
`pydantic` (transitive, via several), `aiofiles`.

**Tooling and analysis — a bad resolve is noise, caught in CI, fixed in a
lane:** `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-xdist`, `ruff`,
`scikit-learn`, `scipy`, `Pillow`/`pillow` (declared twice, in two cases),
`pystray`, `json-repair`, `packaging`, `pyyaml`, `typing-extensions`.

## What to do, and what NOT to do

**Do:** put an upper major bound on the serving-path group only, matching what
the daemon container actually runs today — the same move #2746 made for
fastmcp, and the same bound the plugin runtime already had. Each one wants the
version production serves recorded next to it, so the bound has evidence rather
than a guess.

**Do:** fix the duplicate `Pillow>=10.0` / `pillow>=10.0` while in there; two
spellings of one dependency is the same family of defect as two spellings of
one authority key.

**Do not** pin the tooling group. A stale test runner or linter costs more than
it saves, and CI is where those breakages are supposed to surface.

**Do not** reach for a full lockfile as the first move. It is a bigger change
than this needs, it has to be maintained by whoever adds a dependency, and the
failure it prevents is already prevented by an upper bound on eight packages.
Revisit if a second unbounded package bites.

## The tell for next time

The signature of this failure is **CI red on every open PR with no commit that
could explain it**. When that happens, read the `Install` step's resolved
versions before reading any test output — the diff is in what pip chose, not in
the tree.
