# `/mcp-directory*` Retirement Review

Date: 2026-07-24  
Lane: `codex/retire-mcp-directory`  
Scope: OpenSpec tasks 6.1–6.4 and the removal-related portion of 7.1–7.4

## Authority

The host confirmed that the exact public name is `TinyAssets`, the sole public
remote endpoint is `https://tinyassets.io/mcp`, and every
`/mcp-directory*` route retires promptly to ordinary absent-route 404
behavior. Redirects, proxies, aliases, translations, 410 responses, and
compatibility bodies are forbidden.

## Independent review

Codex independent diff review initially returned `NEEDS WORK` because current
OpenAI runbooks and PLAN still described the retired directory product, and
because the broad test/lint gates had not been evidenced. The slice corrected
the current runbooks and PLAN. Ruff comparison then proved that the changed
files add no non-`E501` debt and do not increase their pre-existing `E501`
counts.

Claude Opus 5 independently reviewed the corrected slice twice:

1. The first review returned `APPROVE WITH NONBLOCKING NOTES` after
   independently running 214 focused Python tests, 61 Worker tests, strict
   OpenSpec validation, registry/package parity, and changed-file lint
   comparison.
2. A narrower rereview returned `APPROVE WITH NONBLOCKING NOTES` after
   independently proving provider-free ASGI initialization and exact-seven
   enumeration, 61 Worker tests, Claude plugin mirror parity, 125 focused
   runtime tests, 89 parity/admission/auth tests, and no new Ruff debt.

The rereview identified one current documentation defect: the operator-request
inventory still spoke of two current public MCP mounts. This slice now labels
the two-mount observation as pinned pre-retirement evidence and records the
one-mount post-retirement truth. It also identified canonical spec drift. The
removal-only requirements are therefore folded into
`openspec/specs/live-mcp-connector-surface/spec.md` now; the broader future
hardening and distribution requirements remain unsynced until their
implementation and external evidence are truthful.

Three focused Codex read-only follow-ups then approved the final boundaries:
one verified deployment/probe coverage and a secretless Wrangler dry-run, one
verified the partial OpenSpec sync and operator inventory, and one verified
current guidance, exact discovery naming, and historical proof fences. Their
initial findings were fixed before their approval; approval was not inferred
from the first pass.

## Verification evidence

Fresh local evidence on Windows/Python and Node, 2026-07-24:

- 245 focused Python tests passed with two pre-existing warnings.
- 61 Cloudflare Worker tests passed.
- 30 deploy-workflow and retired-route probe tests passed.
- 14 action/workflow invariant tests passed.
- MCPB schema validation, pack/import, generated mirror parity, and exact-seven
  enumeration passed.
- MCP Registry official schema validation and generator `--check` passed.
- Wrangler 4.114.0 credential-free dry-run passed.
- Strict OpenSpec validation passed.
- A local Streamable-HTTP canary initialized as exact `TinyAssets` and listed
  exactly seven handles.
- `git diff --check` passed apart from line-ending notices.
- Changed-file Ruff passed when excluding only the unchanged baseline `E501`
  debt; an explicit before/after comparison found no increase.

The broad `python -m pytest -q tests` command was attempted with a 15-minute
limit but did not finish. It is recorded as inconclusive, not passing.
Targeted evidence above and configured CI remain the merge authority.

## Production pre-image

Read-only production probes on 2026-07-24 showed why deployment proof remains
open:

- canonical `/mcp` still initialized with lowercase `tinyassets`;
- `/mcp-directory*` returned Cloudflare 403 error 1010 rather than ordinary
  404.

These are pre-deployment observations. Tasks 6.5 and Sections 5 and 7 remain
open until the merged production revision is deployed, canonical and retired
route canaries pass, maintained registrations are repointed or withdrawn, a
rendered supported-chatbot conversation is recorded, and post-fix user or
watch evidence exists.

## Foldback boundary

This is a partial behavioral sync, not completion of the encompassing change.
It removes already-deleted directory behavior from canonical as-built truth.
It does not claim that public status projection, neutral instructions, OAuth
metadata/enforcement, registry publication, host acceptance, concurrency
proof, or post-fix organic use are complete. OpenSpec task 7.4 therefore
remains unchecked and the change remains active.
