---
title: Compliance Template Brain Conventions Seed
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 483
wiki_source: pages/design-proposals/design-005-compliance-template-brain-conventions-seed-7-user-authored-w.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#retrieval-and-memory
  - docs/catalogs/privacy-principles-and-data-leak-taxonomy.md
  - docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md
---

# Compliance Template Brain Conventions Seed

## 1. Recommendation Summary

Accept the request as a community-build design seed: add seven
user-authored worked-example pages to the public wiki/brain for common
compliance-adjacent workflow patterns:

- HIPAA-adjacent health records
- GDPR-adjacent personal data
- SOX-adjacent financial controls
- SOC 2-adjacent vendor/security evidence
- PCI-adjacent payment-card handling
- FERPA-adjacent education records
- Attorney-client privilege / legal confidentiality

These pages should be treated as reusable conventions and examples that a
chatbot can consult while composing a user's workflow from existing
primitives. They should not become platform compliance modes, sensitivity
tiers, new MCP actions, new evaluator kinds, or server-side policy templates.

This matches PLAN.md's current scoping rules: privacy and threat-model
patterns are community-build; the platform owns enforcement chokepoints and
evidence surfaces, while the community evolves domain patterns in its own
language.

## 2. Proposed Page Contract

Each worked-example page should use the same structure so retrieval can
surface it predictably and chatbots can remix it without inventing missing
policy.

Recommended sections:

1. `What this helps with` - the user-facing workflow shape, not a legal claim.
2. `Non-goals` - explicitly says it is not legal advice, certification,
   attestation, or a guarantee of compliance.
3. `Data to keep host-resident` - examples of instance data that should stay
   private and why.
4. `Public concept layer` - patterns that are safe and useful to publish to
   the commons, such as node topology, checklist shape, audit-step names, and
   evaluation rubrics without user data.
5. `Questions the chatbot asks first` - short prompts that elicit authority,
   data category, destination, retention, provider-routing, and publication
   intent.
6. `Composition pattern` - how to compose the workflow with existing nodes,
   branches, evaluators, gates, provider allowlists, and privacy-decision
   evidence.
7. `Worked example` - a concrete but synthetic scenario with no real PII,
   secrets, regulated records, client confidences, or copyrighted payloads.
8. `Failure modes` - how the workflow can go wrong, including accidental
   publication, third-party provider fallback, overclaiming compliance, and
   missing user authority.
9. `Review checklist` - what an opposite-provider checker or human reviewer
   should verify before promoting the page.

The pages should be tagged consistently, for example:

```yaml
type: brain-convention
domain: compliance-template
jurisdiction_or_framework: HIPAA
content_class: worked-example
legal_status: not-legal-advice
privacy_default: instance-data-host-resident
platform_surface: existing-primitives-only
```

The exact wiki frontmatter can follow current wiki conventions, but the
semantic fields above are the required retrieval contract.

## 3. Seven Page Seeds

### HIPAA-Adjacent Health Records

Focus on patient or health-plan data. The page should bias toward keeping
patient identifiers, diagnoses, clinical notes, claims, appointment details,
and provider-specific account data host-resident. Publishable concept material
can include intake-review topology, de-identification checklist shape, and
audit-gate phrasing.

### GDPR-Adjacent Personal Data

Focus on personally identifying data, data-subject requests, retention,
erasure, export, lawful-basis notes, and cross-border processing questions.
The page should distinguish reusable request-handling workflow concepts from
actual data-subject identity, request contents, and controller/processor
facts.

### SOX-Adjacent Financial Controls

Focus on change control, access review, evidence collection, segregation of
duties, and audit packet preparation. The page should avoid claiming SOX
readiness; it should help users compose evidence workflows while keeping
company-specific ledgers, employee names, control failures, and auditor
communications private.

### SOC 2-Adjacent Security Evidence

Focus on vendor/security control evidence, policy review, incident-response
traceability, and evidence freshness. Publishable material can include control
mapping patterns and evidence-staleness gates. Private material includes
customer lists, vendor contracts, security architecture details, vulnerability
findings, and internal tickets.

### PCI-Adjacent Payment-Card Handling

Focus on minimizing card-data exposure. The page should strongly prefer
workflows that avoid storing or processing cardholder data in Workflow at all.
If a user insists on a payment-card-adjacent workflow, the chatbot should ask
about tokenization, processor boundaries, logs, screenshots, exports, and
third-party provider routing before any write.

### FERPA-Adjacent Education Records

Focus on student records, grades, advising notes, school identifiers, and
guardian/parent access context. Publishable concepts can include request
triage and record-review flow. Student-specific records and institutional
access decisions stay private.

### Attorney-Client Privilege / Legal Confidentiality

Focus on privileged communications, legal strategy, matter names, client
identity, work product, conflict checks, and sharing boundaries. The page
should emphasize preserving confidentiality and avoiding public reuse of any
facts that could reveal a client, matter, or strategy. Publish only generic
workflow topology and synthetic examples.

## 4. Platform Boundary

This proposal intentionally does not add runtime code.

The chatbot can already compose these patterns from existing primitives and
wiki retrieval. The platform should not ship pre-baked `hipaa_mode`,
`gdpr_mode`, `sox_mode`, `soc2_mode`, `pci_mode`, `ferpa_mode`, or
`attorney_privilege_mode` flags. Those would freeze policy taxonomy in
platform code and conflict with the privacy-via-community-composition rule.

Platform work remains appropriate only at enforcement chokepoints, such as:

- provider routing allowlists that prevent silent third-party fallback;
- upload/write allowlists and filesystem path enforcement;
- field-level visibility and training-exclusion enforcement;
- structured privacy-decision evidence and caveats;
- moderation or abuse handling for unsafe public wiki content.

The worked examples are inputs to chatbot reasoning, not enforcement
mechanisms.

## 5. Safety And Review Gates

Before any of the seven pages is promoted beyond proposal/draft status, the
checker should verify:

1. The page contains no real PII, PHI, cardholder data, education record,
   client confidence, credential, or confidential business fact.
2. Every domain-specific assertion is phrased as workflow guidance, not as
   legal advice, certification, attestation, or compliance guarantee.
3. The page names its non-goals and tells the chatbot to ask for user authority
   when regulated, privileged, or third-party data appears.
4. The composition uses existing Workflow primitives and wiki retrieval only.
   Any proposed new primitive is split into a separate design request and must
   pass the PLAN.md scoping rules.
5. The example uses synthetic data and clearly labels it as synthetic.
6. The privacy recommendations align with
   `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md`, especially
   T1 through T4.
7. An opposite-family reviewer checks the page text before publication when
   the page is authored by an automated daemon.

For this request's bounty ladder, the design-only artifact is complete when
the proposed note exists, the seven page contracts are explicit, and the
runtime non-goal is clear. Any later implementation bounty should attach to
creating or reviewing the wiki pages, not to this design note.

## 6. Open Questions

1. Should the seven pages live under a single `compliance-template` wiki
   namespace, or should they live beside other domain brain conventions with a
   shared tag? Recommendation: use shared tags first; add a namespace only if
   wiki navigation needs it.

2. Should each page name external statutes/frameworks directly? Recommendation:
   yes for discoverability, but only as "adjacent" or "inspired by" workflow
   categories unless reviewed by qualified counsel.

3. Should pages include jurisdiction-specific variants, such as EU GDPR vs UK
   GDPR or state privacy laws? Recommendation: not in the seed. Add variants as
   separate community remixes after the base page pattern is proven.

4. Should compliance worked examples be eligible for autoresearch? Recommendation:
   yes for finding public explanatory sources, but no generated legal claims
   should be promoted without explicit review.

## References

- Issue #483
- PR artifact receipts #678 and #679
- `PLAN.md` Scoping Rules
- `PLAN.md` Retrieval And Memory
- `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md`
- `docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md`
