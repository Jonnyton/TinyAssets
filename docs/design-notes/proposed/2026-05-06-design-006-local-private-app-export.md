# Design-006 Proposed: Local-Private App Export

Status: Proposed
Date: 2026-05-06
Source: WIKI-DESIGN / Issue #484
Wiki path: `pages/design-proposals/design-006-local-private-app-export-desktop-binary-post-export-learning.md`

## Classification

Project design. This note does not authorize runtime code changes. It scopes the
local-private app export idea into a post-gate sequencing plan so implementation
can be evaluated after PR-048, PR-049, and FEAT-002 have landed and been
freshness-checked.

## Context

The request asks for a local-private app export path: a user should be able to
turn a Workflow branch into a desktop binary, run it locally with private data,
let the daemon learn useful post-export patterns, and support privacy-preserving
billing for daemon calls.

Current PLAN.md constraints shape the answer:

- The user capability axis distinguishes browser-only users from local-app
  users; export targets the local-app tier first and must not become the only
  way to use a workflow.
- Privacy is host-resident and commons-first. Private data belongs on user or
  host machines; platform-stored data is public-by-definition.
- Privacy policy is community-composed, but platform-owned enforcement
  boundaries still matter: local routing, upload/write boundaries, MCP approval,
  and host capability declarations are primitives.
- Distribution layers wrap the same portable daemon core. Desktop binaries,
  MCPB packages, plugins, and future package formats must not fork the engine or
  tool surface.
- Monetization is currently the paid-market settlement rail. No subscription,
  premium feature gating, or fiat billing model should be introduced by this
  proposal.

## Proposed Shape

Local-private app export is a packaging profile over existing Workflow
artifacts, not a new authoring model.

An exported app bundle contains:

- A frozen public concept layer: goal, branch, node definitions, evaluator
  references, attribution metadata, license metadata, and required capability
  declarations.
- A local runtime profile: approved providers, local-only routing constraints,
  allowed file roots, required external software, and offline behavior.
- A private instance store created at first run on the user's machine. This
  store holds user data, private outputs, daemon memory specific to the export,
  and routing audit events.
- A manifest that records the source branch version, export timestamp, package
  format, and compatibility floor for the daemon/runtime.

The desktop binary is therefore an install artifact for a branch snapshot. It
does not make private rows in the platform database, does not create a private
catalog entry, and does not require the platform to inspect private content.

## Post-Export Learning

The daemon may learn after export, but learning is split by visibility:

- Private learning remains in the exported app's local instance store.
- Public learning can be proposed back to the commons only as concept-layer
  patches, stripped of private examples, file paths, credentials, and user data.
- The user or host must approve any publish-back action. Default export behavior
  is local-only learning.
- Published improvements preserve attribution to the source branch and exported
  app lineage without exposing private run data.

This keeps the useful part of post-export learning in the community loop while
preserving the architectural rule that private content never becomes
platform-resident.

## Privacy-Preserving Daemon-Call Billing

Billing should meter daemon calls without disclosing private payloads.

For v1, the billing record should be a minimal settlement envelope:

- requester or local installation identity
- daemon or host identity
- source branch/package identity
- capability class and rough resource class
- timestamp and settlement amount
- non-content call receipt hash

The envelope must not include prompts, file names, private outputs, raw logs, or
derived summaries of private content. Dispute and audit flows can prove that a
call happened using receipts and local audit logs, but content disclosure remains
an explicit user-controlled export from the local app.

Self-hosted local calls stay on the existing no-fee path. Paid calls to another
daemon use the paid-market settlement rail and platform fee model already
defined in PLAN.md; this proposal does not add a subscription or premium tier.

## Sequencing

Do not implement this before the named upstream gates have landed and been
checked against current code:

1. PR-048 lands.
2. PR-049 lands.
3. FEAT-002 lands.
4. Re-check PLAN.md scoping rules, host-resident private data design, desktop
   tray specs, and paid-market settlement specs for drift.
5. Write an implementation spec with exact files, package format, manifest
   schema, local store location, billing envelope fields, and acceptance tests.
6. Only then dispatch code work.

The first implementation slice should be manifest-only export planning:

- define the export manifest schema
- produce a dry-run bundle plan for one public branch
- prove no private content enters the manifest
- run package/build checks without producing an installer

Desktop binary build, updater behavior, publish-back UX, and paid daemon-call
settlement should remain later slices.

## Non-Goals

- No new MCP action is proposed by this note.
- No runtime code change is authorized by this note.
- No platform-side private data store.
- No private catalog rows or soft-private branches.
- No subscription, premium gating, or fiat billing.
- No replacement for browser-only workflows.
- No forked engine for exported apps.

## Open Questions

- What exactly do PR-048, PR-049, and FEAT-002 contain, and which acceptance
  evidence proves they landed?
- Which package format is first: existing desktop/plugin packaging, a standalone
  installer, or a manifest-only dry run?
- What local store format should exported apps use so users can inspect,
  migrate, or delete private data?
- What receipt hash scheme is sufficient for billing disputes without leaking
  content?
- What publish-back review UX prevents private examples from being smuggled
  into concept-layer patches?

## Acceptance Gates For A Future Build

- Freshness-stamped proof that PR-048, PR-049, and FEAT-002 have landed.
- Manifest dry-run test showing private content is excluded.
- Local-only routing test for confidential exports.
- Billing-envelope test proving no prompt, file path, output, or private log
  field is serialized.
- Desktop package smoke on at least one supported local-app host.
- Browser-only caveat documented so the feature does not regress tier-1 users.
