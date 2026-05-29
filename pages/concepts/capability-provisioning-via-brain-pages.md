---
title: Capability Provisioning Via Brain Pages
type: concept
status: proposed
created: 2026-05-29
source_issue: 1194
source_patch_request: PR-163
tags: [capabilities, skills, mcp, lsp, brain, user-buildable]
---

# Capability Provisioning Via Brain Pages

## Purpose

Skills can be shared as text today, but many useful skills also assume runtime
capabilities that do not travel with the skill: MCP servers, LSP-backed tools,
or host-specific telemetry adapters. A user who can fork a skill through brain
pages still cannot express "this skill needs Serena" or "this daemon serves
Context7" in a portable way.

This concept extends [[skill-sync-via-brain-pages]] from skill text to the
capability layer that skill text depends on.

## Recommendation

Use brain pages as the canonical exchange record for portable capability
requirements and declarations. Local runtime configuration remains a
projection, not the semantic source of truth.

A portable capability page should describe one attachable capability in a
runtime-neutral form:

- `capability_id`: stable lower-case identifier, for example `serena` or
  `context7`
- `kind`: `mcp_server`, `mcp_lsp_bridge`, `lsp`, or `runtime_bound`
- `portable`: boolean; false for telemetry or harness-private capabilities
- `scope`: user, branch, daemon, host, commons, or another bounded Scope
- `transport`: stdio, streamable-http, sse, or host-native
- `launch`: command/args, URL, or connector reference needed by runtimes that
  can materialize it
- `runtime_projections`: Claude Code plugin/MCP config, Cowork connector,
  Codex `config.toml [mcp_servers.*]`, raw MCP URL, or other known projections
- `review_gate`: required checker family or review rule before adoption
- `security_notes`: filesystem, network, token, subprocess, or telemetry
  implications visible to reviewers

Skill frontmatter may then declare:

```yaml
requires_capability:
  - serena
  - context7
```

The requirement is declarative. It does not silently install software, grant
tokens, or bypass a host's runtime approval surface.

## Relationship To Existing Capability Designs

This is not a replacement for node software capabilities in
`docs/design-notes/2026-04-15-node-software-capabilities.md`.

That design covers work nodes that need local software such as Unreal Engine,
Blender, Ollama, or Docker to execute. This concept covers agent-runtime
capabilities that make skills usable across MCP hosts and local agent runtimes.
They can share vocabulary (`required_capabilities`, `served_capabilities`,
Scope attachment, review gates), but they resolve to different projections.

## Projection Rules

Each runtime materializes only the projections it understands:

- Claude Code: plugin metadata or MCP server configuration
- Cowork: connector configuration or raw MCP endpoint when supported
- Codex: `~/.codex/config.toml` entries under `[mcp_servers.*]`
- Other MCP clients: raw MCP URL, stdio command, or documented unsupported
  caveat

Runtime-bound capabilities must say so explicitly. For example, a
session-report capability that parses Claude Code transcripts is not portable;
its page can still exist, but `portable: false` prevents the brain record from
pretending Codex or Cowork can materialize it.

## Mark-Lane Acceptance Test

A user without project-folder access can attach or fork a capability using
brain primitives alone:

1. The user forks or proposes a skill page that declares
   `requires_capability`.
2. The user attaches an accepted or proposed capability page to the same
   Scope.
3. A runtime-specific checker reports whether the current host can materialize
   the capability and shows the projection it would use.
4. If materialization is unsupported or runtime-bound, the checker returns a
   structured caveat instead of silently claiming success.

## Non-Goals

- No new MCP handle is required yet. Existing `read.page` and `write.page`
  can carry proposed capability pages while the primitive shape is tested.
- No cross-runtime plugin wrapper becomes canonical. Claude Code plugins,
  Cowork connectors, and Codex config entries are projections.
- No automatic install or token grant is implied by reading a capability page.
- No platform-owned catalog freezes the policy. Community pages can evolve
  capability records through normal review.

## Adoption Path

1. Add one portable accepted canary capability page for an MCP server that
   already works across runtimes, such as Serena or Context7.
2. Add a read-only checker that validates capability page fields and reports
   known runtime projections without writing local config.
3. Teach skill projection checks to fail loudly when an accepted skill declares
   a missing `requires_capability`.
4. Only after checker evidence is stable, allow accepted capability pages to
   materialize runtime projections through explicit host approval.

## References

- GitHub issue #1194
- `pages/patch-requests/pr-163-capability-provisioning-should-be-a-portable-user-buildable-.md`
- [[skill-sync-via-brain-pages]]
- `docs/design-notes/2026-04-15-node-software-capabilities.md`
- `PLAN.md` - Canonical Vocabulary
- `PLAN.md` - User capability axis
