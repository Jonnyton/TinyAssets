---
title: Work Primitive Industry Framing
date: 2026-05-06
status: noted
source: pages/concepts/work-primitive-industry-framing-jones-2026-05-06.md
source_updated: 2026-05-06T23:32:30.282233Z
source_sha256: 5ac354ef07478a0d66d5725f102d473603ba39544f98aefac07e31b9197b52dc
github_issue: 568
request_id: WIKI-DOCS
---

# Work Primitive Industry Framing

The promoted wiki concept frames TinyAssets' substrate as a way to define
agent-native work primitives: durable, permissioned, reviewable units of work
that agents can inspect, mutate, run, and document without being limited to
one-shot UI operation.

This is docs/ops framing, not a runtime change request. It does not introduce
a new primitive or MCP action. It gives a public explanation for the existing
direction:

- Six base concepts, `Node`, `Edge`, `State`, `Scope`, `Run`, and `Trigger`,
  describe work at the graph layer.
- Five access handles, `read.graph`, `write.graph`, `run.graph`, `read.page`,
  and `write.page`, are the intended chatbot-facing control surface for those
  composed work primitives.
- The access, meaning, and authority split maps to current cross-client MCP
  alignment, substrate vocabulary, and scope-decoration work.

The practical test from the concept page is whether users and daemons build a
durable work graph above underlying apps, rather than only operating app
interfaces in a single session. That test lines up with the current community
loop and brain-commons work: successful substrate should make non-coding work
feel as inspectable, reusable, and feedback-rich as a codebase.

## Follow-Through

Use this framing when explaining the substrate work externally: TinyAssets lets
users compose reusable work primitives from a small graph vocabulary, and lets
agents act on those primitives through a small permissioned handle set.

No PLAN.md update is made here because this page restates current direction
rather than accepting a new architecture decision.
