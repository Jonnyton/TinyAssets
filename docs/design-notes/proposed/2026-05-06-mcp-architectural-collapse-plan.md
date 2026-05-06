---
title: MCP Architectural Collapse Plan
date: 2026-05-06
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 537
wiki_source: pages/notes/codex-response-cowork-mcp-architectural-collapse-plan-2026-05-06.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#api-and-mcp-interface
  - PLAN.md#distribution-and-discoverability
  - pages/notes/cowork-mcp-architectural-collapse-plan-30-to-5-2026-05-06.md
  - pages/patch-requests/pr-063-pr-063-fold-mcp-server-py-12-tools-legacy-daemon-file-interf.md
  - pages/patch-requests/pr-064-pr-064-fold-directory-server-py-11-tools-app-store-directory.md
  - pages/patch-requests/pr-065-pr-065-single-server-architecture-1-fastmcp-instance-5-handl.md
---

# MCP Architectural Collapse Plan

## 1. Recommendation Summary

Ratify the community wiki direction as a design sequence, not an immediate
runtime patch: collapse Workflow's MCP surface from three overlapping servers
and about thirty registered tools to one FastMCP server with five composable
handles:

- `read.graph`
- `write.graph`
- `run.graph`
- `read.page`
- `write.page`

The three current audiences keep different permissions, not different tool
names:

| Audience | Current surface | Target scope |
|---|---|---|
| User chatbot | `/mcp` via `workflow/universe_server.py` | `chatbot` |
| App-store directory reviewers | `/mcp-directory` via `workflow/directory_server.py` | `directory-submission` |
| Daemon-local control | `workflow/mcp_server.py` | `daemon-local` |

This clears the minimal-primitives test: the platform should expose the fewest
handles that compose the graph/page operations users need. It also clears the
MCP host-coverage test: Claude, ChatGPT, directory reviewers, and daemon-local
clients should all learn one stable interface shape instead of three tool
vocabularies.

This note does not implement the collapse. It defines the landing order,
acceptance gates, and design constraints for PR-047, PR-063, PR-064, and
PR-065 so later code branches do not rediscover or reinterpret the plan.

## 2. Current Evidence

The live code still has three server surfaces as of 2026-05-06 in this
checkout:

- `workflow/universe_server.py` creates the primary `FastMCP` app and mounts
  `/mcp` plus `/mcp-directory`, importing `directory_mcp`.
- `workflow/directory_server.py` creates a separate `directory_mcp` FastMCP
  instance and registers eleven directory-facing tools.
- `workflow/mcp_server.py` creates a separate legacy FastMCP instance and
  registers twelve daemon-file tools.

The wiki filings describe the intended sequence:

1. PR-047: collapse the user-facing `universe_server.py` surface to the five
   handles.
2. PR-063: fold/deprecate `mcp_server.py` and migrate daemon-local/internal
   callers.
3. PR-064: fold `/mcp-directory` onto the same server through scoped auth.
4. PR-065: delete the deprecated server files/entry points and leave one
   FastMCP instance.

The Codex response wiki note concurs with that order, with one nuance:
PR-063 and PR-064 can be designed in parallel after PR-047, but should land
sequentially because PR-064 touches directory/marketplace expectations.

## 3. Target Architecture

### One Server

The final state is one MCP server implementation and one registered FastMCP
tool namespace. Server shells may still route different HTTP paths, but those
paths select session scope; they do not register separate tool sets.

Required invariant:

```text
/mcp            -> same five handles, chatbot scope
/mcp-directory  -> same five handles, directory-submission scope
daemon-local    -> same five handles, daemon-local scope
```

This is a logical-server commitment, not permission to grow a new god-module.
The active wiki filings name `workflow/universe_server.py` because that is the
current shell. The implementation may land in the target module layout
(`workflow/servers/` shell plus `workflow/api/` submodules) as long as the
externally visible invariant remains one FastMCP tool namespace with five
handles.

### Five Handles

The five handles are operation families, not convenience verbs.

| Handle | Owns |
|---|---|
| `read.graph` | status, goals, universes, branches, runs, gates, runtime metadata |
| `write.graph` | branch/node/goal/request mutations that affect graph state |
| `run.graph` | execution, pause/resume, dispatch, and run-control operations |
| `read.page` | wiki, notes, docs, and other page-like commons reads |
| `write.page` | wiki/page writes, patch-request filing, notes/canon page mutations |

Internal Python functions such as branch builders, goal handlers, run
controllers, and page writers stay private implementation. They are not MCP
tool names.

### Scope Policy

Scope decoration must be a real session capability layer, not an ad hoc wrapper
around `/mcp-directory`.

Minimum scopes:

| Scope | Allowed shape |
|---|---|
| `chatbot` | Full public user control surface subject to user/session auth |
| `directory-submission` | Directory-safe reads plus the explicitly approved request/proposal writes |
| `daemon-local` | Host-local daemon control, including approved file/system effects |

The design may reuse existing capability vocabulary where it fits, but memory
scope is not already an MCP session-auth boundary. PR-064/PR-065 should add the
session-scope contract explicitly and test it as an auth decision.

## 4. Landing Order

### Phase 1: PR-047 First

PR-047 is the prerequisite because PR-063 and PR-064 need the five-handle
target to exist. Do not fold legacy callers into a moving or hypothetical
interface.

Acceptance:

- `/mcp` exposes the five handles.
- Legacy user-callable names are gone from the public user-facing MCP surface.
- Existing graph/page operations still dispatch through private Python
  implementation.
- ChatGPT and Claude user-surface smoke tests prove the five handles render
  usable structured content.

### Phase 2: PR-063 Next

PR-063 folds `workflow/mcp_server.py`.

Before implementation, write a migration map that lists each legacy tool and
its five-handle target:

| Legacy tool | Target handle |
|---|---|
| `get_status` | `read.graph` |
| `add_note` | `write.page` |
| `get_premise` | `read.page` or `read.graph`, depending on final premise storage |
| `set_premise` | `write.page` or `write.graph`, matching the read target |
| `get_progress` | `read.graph` |
| `get_work_targets` | `read.graph` |
| `get_review_state` | `read.graph` |
| `get_chapter` | `read.page` |
| `get_activity` | `read.graph` or `read.page`, depending on final log exposure |
| `pause` | `run.graph` |
| `resume` | `run.graph` |
| `add_canon` | `write.page` |

Ambiguous rows must be resolved in the PR-063 migration map before code moves.
The ambiguity is intentional here: this design note should not guess storage
ownership for premise/activity while runtime code is still in transition.

Acceptance:

- Internal callers in `workflow/daemon/`, scripts, tests, and packaging mirror
  stop importing or invoking `workflow.mcp_server`.
- Daemon-local behavior has focused tests through the five-handle surface.
- Any temporary deprecation warning names the exact five-handle replacement.
- No public compatibility alias is added unless the host explicitly reverses
  the no-shims direction.

### Phase 3: PR-064 After PR-063

PR-064 folds `workflow/directory_server.py` through scope decoration.

It can be designed while PR-063 is underway, but it should not land first.
The directory path is a marketplace surface; mixing marketplace route changes
with daemon-local migration noise makes rollback and review harder.

Acceptance:

- `/mcp-directory` routes to the same server and five handles.
- `directory-submission` scope permits only the directory-approved read/write
  shapes.
- Out-of-scope operations fail with structured evidence and a user-safe
  explanation.
- Host-action checkpoint is recorded before production route replacement or
  marketplace resubmission, because reviewer-visible tool names change from
  eleven directory-specific tools to five scoped handles.

### Phase 4: PR-065 Last

PR-065 is the cleanup and invariant branch.

Acceptance:

- `workflow/mcp_server.py` and `workflow/directory_server.py` are deleted or
  reduced to non-public import stubs only if packaging requires an intermediate
  step.
- `python -m workflow.mcp_server` and `python -m workflow.directory_server`
  entry points are removed.
- Startup creates one FastMCP instance.
- Tests prove the three scopes see the same five handles and different
  authorization outcomes.
- Packaging/plugin mirror is rebuilt if runtime files under `workflow/*` are
  touched.

## 5. Gates

The collapse should not be considered done until these gates pass:

| Gate | Required evidence |
|---|---|
| Primitive count | Tool listing shows only five MCP handles for each supported path/scope |
| Scope auth | Allowed and rejected operation tests for `chatbot`, `directory-submission`, and `daemon-local` |
| Cross-client rendering | Claude and ChatGPT smoke proof for the five-handle user surface |
| Directory safety | `/mcp-directory` proof plus host marketplace coordination note |
| Daemon-local continuity | Focused tests replacing the twelve legacy daemon-file tools |
| Structured content | Every handle returns structured content usable by both primary MCP hosts |
| Rollback clarity | Each phase can be reverted independently until PR-065 deletes legacy surfaces |

For public MCP behavior, final acceptance still needs the project-standard
rendered chatbot conversation through the live connector. Direct MCP probes are
supporting evidence, not the final user-surface proof.

## 6. Tradeoffs

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep three servers and patch structured content everywhere | Lowest immediate architecture churn | Permanent tool-count inflation, repeated cross-client fixes, more marketplace/user confusion | Reject |
| Collapse user surface only | Helps chatbot users quickly | Leaves directory and daemon-local surfaces as divergent long-term contracts | Reject as final state |
| One server, five handles, scoped sessions | Matches minimal-primitives, cross-client parity, and directory constraints | Requires careful auth/session-scope design and phased migration | Recommend |
| Delete legacy servers immediately after PR-047 | Fast cleanup | Risks daemon-local and directory regressions without migration maps | Reject |

## 7. Open Questions

1. Should premise and activity live under `read.page`/`write.page` or
   `read.graph`/`write.graph` after PR-063?

   Recommendation: decide from storage ownership. If the artifact is page-like
   and user-editable as text, use page handles. If it is live graph/runtime
   state, use graph handles.

2. Can `/mcp-directory` expose the same five tool names to marketplace
   reviewers without delaying approval?

   Recommendation: require a host-action checkpoint before production route
   replacement. The architecture should be ready, but marketplace timing is a
   deployment gate.

3. Where should session scope be represented?

   Recommendation: add a small explicit MCP session-scope policy near the auth
   middleware/transport boundary, then pass capability evidence into handlers.
   Do not encode scope as route-specific branching inside individual tools.

4. Should compatibility aliases exist for old tool names?

   Recommendation: no for public MCP. This is pre-public enough to favor a clean
   break. Temporary internal deprecation warnings are acceptable only while
   PR-063/PR-064 migrate callers.

## References

- `PLAN.md` Scoping Rules
- `PLAN.md` API And MCP Interface
- `PLAN.md` Distribution And Discoverability
- `docs/design-notes/2026-04-22-mcp-tool-surface-scaling.md`
- `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md`
- `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`
- Wiki: `pages/notes/cowork-mcp-architectural-collapse-plan-30-to-5-2026-05-06.md`
- Wiki: `pages/notes/codex-response-cowork-mcp-architectural-collapse-plan-2026-05-06.md`
- Wiki: `pages/patch-requests/pr-063-pr-063-fold-mcp-server-py-12-tools-legacy-daemon-file-interf.md`
- Wiki: `pages/patch-requests/pr-064-pr-064-fold-directory-server-py-11-tools-app-store-directory.md`
- Wiki: `pages/patch-requests/pr-065-pr-065-single-server-architecture-1-fastmcp-instance-5-handl.md`
