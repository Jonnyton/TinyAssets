---
title: Deploy As Branch
date: 2026-05-11
author: codex-wiki-design
status: proposed
request_id: WIKI-PATCH
github_issue: 802
wiki_source: pages/patch-requests/pr-110-pr-110-deploy-restart-cycle-should-be-a-user-redesignable-br.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#uptime-and-alarm-path
  - docs/design-notes/2026-04-18-full-platform-architecture.md#25-2-automated-deploy-pipeline-zero-human-gate-for-green-ci-changes
---

# Deploy As Branch

## 1. Classification

Issue #802 is a project-design patch. The request title asks for the
deploy/restart cycle to become a user-redesignable Branch. That changes the
operational model for production release and self-healing paths, so the
smallest safe repository change is this proposed design note. It does not
justify runtime code changes on the issue body alone.

The referenced wiki page is not present in this checkout as of 2026-05-11, and
issue #802 has no comments. This note therefore scopes from the issue title and
the existing PLAN.md uptime architecture.

## 2. Problem

Workflow's uptime plan already treats deploy, restart, rollback, canary checks,
and incident escalation as first-class operational responsibilities. Today that
logic is mostly encoded in GitHub Actions, systemd/watchdog behavior, runbooks,
and skills. Those surfaces can be reviewed by contributors, but they are not
yet shaped like normal Workflow work: Branches with nodes, gates, evidence,
lineage, and user-remixable alternatives.

That creates a product mismatch. If Workflow is meant to let users and daemons
redesign substantive multi-step work, the project's own deploy/restart loop
should be explainable and improvable through the same Branch vocabulary. The
platform should not special-case its most important recurring workflow as an
opaque ops script forever.

## 3. Design Contract

Deploy-as-Branch means the deploy/restart cycle is represented as a public
operations Branch in the commons. The Branch describes the release path as
ordinary workflow nodes:

- select candidate change;
- verify required gates;
- build deploy artifact;
- deploy or restart;
- run canaries and user-surface checks;
- rollback or escalate on failure;
- record post-fix clean-use evidence;
- publish incident or release evidence.

The Branch is user-redesignable at the design layer: users and daemons may fork,
propose, compare, and improve deploy/restart Branch variants. A variant becoming
the production-bound deploy path still requires the existing safety gates:
review authority, secret access, environment permissions, and uptime/load proof.

In other words, Branches can redesign the recipe; they do not bypass production
authorization.

## 4. Fit With PLAN.md

This follows the scoping rules because it does not add a new MCP action or
platform primitive. It reuses Branch, node, run, gate, evidence, and lineage
concepts to model an operational workflow that already exists.

It follows the uptime architecture because deploy-side invariants and the
alarm path remain mandatory. The representation becomes remixable, but the
production execution path must still preserve:

- host-independent recovery;
- no host-only production buttons;
- canary evidence after deploy or restart;
- rollback/escalation paths for failed checks;
- the §14/S7 load and auto-healing proof for uptime-track changes.

It also strengthens community-build over platform-build. The platform should
provide enough substrate for users to evolve release policies in public rather
than baking one permanent deploy policy into hidden automation.

## 5. Minimal Implementation Path

A later implementation should start with documentation and exported structure,
not runtime rewrites:

1. Create a public operations Branch definition for the current deploy/restart
   path, mapping each existing GitHub Actions, watchdog, canary, and rollback
   step to a node with named evidence outputs.
2. Mark the production-bound edges as privileged: only approved maintainers or
   council-equivalent roles can bind a Branch variant to live deploy triggers.
3. Add a comparison page or wiki page that lets users inspect proposed variants
   against the current production-bound Branch.
4. Only after the Branch representation matches current behavior, consider
   letting deploy automation read a reviewed Branch snapshot as configuration.

This order avoids the unsafe jump from "ops scripts exist" to "user-authored
Branch directly drives production."

## 6. Acceptance Checks For Runtime Work

Any runtime implementation that follows this note should prove:

1. The exported Branch exactly matches the current deploy/restart behavior or
   records every intentional difference.
2. A user can fork or propose a Branch variant without gaining production deploy
   authority.
3. Binding a variant to production requires explicit review and environment
   permission.
4. Failed canary, failed restart, rollback, and incident-escalation paths are
   represented as Branch nodes, not hidden side effects.
5. Uptime-track changes include the required concurrency/load proof, including
   the auto-healing scenario from the full-platform architecture.

For public MCP or chatbot-facing changes, final acceptance still requires a
rendered chatbot conversation through the live connector plus post-fix clean-use
evidence, per AGENTS.md.

## 7. Non-Goals

- No change to production deploy workflows in this branch.
- No restart, rollback, or CI automation change in this branch.
- No new MCP action.
- No weakening of maintainer/council/environment authorization.
- No redesign of community-authored Branch content from the missing wiki page.

## 8. Open Questions

1. Should the first exported operations Branch live as a wiki page, a checked-in
   YAML artifact, or both?
2. Which role can approve binding a deploy Branch variant to production:
   maintainers, moderator council, or a future operations council?
3. Should deploy Branch variants be ranked by historical uptime evidence,
   review score, or both?

Recommendation: start with a wiki page plus checked-in generated snapshot. The
wiki page stays user-editable; the checked-in snapshot is what release
automation may eventually consume after review.

## Verification

This is documentation-only:

- No Python files are touched.
- No runtime tests or plugin rebuild are required.
- Review should confirm the note preserves current production authorization and
  does not imply user-authored Branches can directly execute deploys.
