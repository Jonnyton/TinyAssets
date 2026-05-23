---
title: Standards Rule Packs Over Generic Receipts And Gates
type: concept
status: proposed
created: 2026-05-23
source_issue: 1025
source_wiki: pages/design-proposals/design-009-standards-rule-packs-over-generic-receipts-and-gates.md
tags: [standards, conformance, receipts, gates, evaluation]
---

# Standards Rule Packs Over Generic Receipts And Gates

## Purpose

Workflow should treat external standards as versioned community-remixable rule
packs layered above a small platform substrate, not as one core table or
primitive per industry. The substrate stays generic: branch versions, run
receipts, evidence handles, gates, evaluators, and artifact references. Domain
standards define their own validation and evidence requirements in packs.

This page preserves DESIGN-009 in the brain surface so adjacent work can align
without prematurely adding `docs/design-notes/proposed/` architecture or
runtime schema.

## Core Distinction

The host standards list mixes different kinds of rules:

- legal, privacy, and security obligations
- management-system and control frameworks
- interoperability, data, metadata, and terminology standards
- reporting checklists and research-practice principles

Workflow can be compatible with these patterns at the platform layer by
collecting controls, evidence, validator output, and audit trails. Actual
compliance is scoped to a deployment, data class, jurisdiction, actor role,
operating procedure, and often an outside reviewer or regulator.

## Claim Levels

Standards packs should not silently convert evidence into a stronger claim.
Use explicit claim levels:

- `compatible`: Workflow can store, map, validate, or export data in the
  standard's shape.
- `control_ready`: Workflow can collect the evidence needed for a compliance
  program, including policies, logs, receipts, approvals, and tests.
- `attested`: a named accountable actor or accepted review process has approved
  the evidence for a scoped environment.

No pack may upgrade a branch, run, artifact, or deployment from `compatible` to
`attested` without explicit accountable acceptance.

## Pack Contract

A standards pack is a versioned artifact, not a core platform feature. A pack
should declare:

- `standard_id`, authority, version, effective dates, supersession, and trust
  level
- jurisdiction, domain, scope, legal status, data classes, actor roles, and
  license or access limits
- controlled vocabulary, ontology, profile, schema, or terminology references
- control, checklist, reporting, retention, disclosure, and rights-request
  requirements
- validator and evaluator branch references
- required evidence handles and accepted evidence types
- migration and deprecation recipes
- exception, risk-acceptance, renewal, and expiry rules

Pack-specific extension metadata belongs in bounded payloads owned by the pack.
Core receipt and gate tables should preserve unknown extension metadata without
validating every standard-specific field.

## Reusable Primitives

The concept should compose from the fewest reusable objects:

- `StandardPack`: versioned rule-pack artifact.
- `DataClassPolicy`: reusable labels and handling policy for sensitive or
  regulated data classes.
- `EvidenceHandle`: reference to logs, validator output, attestations, source
  documents, approvals, hashes, signatures, or outside audit material.
- `Receipt`: append-only event for acquisition, lineage, validation, consent,
  authorization, disclosure, migration, retention, deletion, exception, risk
  acceptance, or conformance.
- `ConformanceClaim`: scoped assertion over a branch, run, artifact, or
  deployment with status, evidence, exceptions, accountable actors, and renewal
  date.
- `PackMigration`: version-to-version recipe that diffs requirements, queues
  updates, reruns validators, preserves old evidence, and writes transition
  receipts.

Publication readiness, clinical-trial readiness, FAIR dataset checks, PCI
self-assessment, or FHIR profile validation should be pack instances over this
substrate, not permanent journal-specific or industry-specific platform
primitives.

## Platform Capabilities Needed

The platform should grow reusable support where the generic substrate is
insufficient:

- a standards registry with authority URL, license, normative or guidance
  status, effective dates, supersession graph, and pack trust level
- artifact and field data classification
- role and obligation modeling for scoped claims
- policy-as-data for purpose limits, consent, disclosure, opt-out, retention,
  legal holds, export controls, and visibility defaults
- deterministic validators plus model-assisted evaluator evidence with reviewer
  identity and confidence
- vocabulary, schema, profile, and terminology references
- evidence-room export with pack version, scope, control matrix, evidence
  handles, exceptions, signatures, and freshness stamps
- branch update flow when a pack version changes

Model-assisted review can contribute evidence, but it is not final compliance
truth unless the pack and accountable review path explicitly accept it.

## Adjacent Work Implications

- PR #1021 should stay a generic run-receipt substrate. It should preserve
  bounded unknown extension metadata and avoid embedding standard-specific
  schema.
- PR #1023 and PR #1001 should treat evidence visibility and gate evidence as
  reusable handles usable by standards packs.
- PR #986 publication-readiness should be treated as a candidate
  `StandardPack` instance or evaluator branch, not a permanent
  journal-specific core primitive.
- PR #991 goal-bound branch protocols and typed handoffs should remain usable
  by pack migrations and evidence-room exports.
- PR #996 selector branches should support conversational pack selection and
  remix without adding one selector action per standard.
- PR #1006 and PR #1007 provenance/local registry work should align with pack
  authority, license, and trust-level metadata.
- PR #1024 chain-exhaustion design applies to pack evaluators: provider
  exhaustion should create retryable receipts or deferred evidence, not corrupt
  conformance state.

## Guardrails

- Do not add one core table, MCP action, or evaluator kind per external
  standard.
- Do not present Workflow as certified or compliant without scoped attestation.
- Do not store private regulated content in the platform commons; packs may
  describe host-local evidence and policies.
- Do not let pack updates mutate branch state opaquely. Updates must produce
  migration diffs, queued work, validator reruns, and receipts.
- Do not collapse standard compatibility, control readiness, and attestation
  into one boolean gate.

## References

- GitHub issue #1025
- DESIGN-009 wiki page:
  `pages/design-proposals/design-009-standards-rule-packs-over-generic-receipts-and-gates.md`
- PR #1021, #1023, #1001, #986, #991, #996, #1006, #1007, #1024
- `PLAN.md` Scoping Rules
- `PLAN.md` Module: Goals & Gates
- `PLAN.md` Module: Evolution & Evaluation
- `PLAN.md` Reference: State & Artifacts
