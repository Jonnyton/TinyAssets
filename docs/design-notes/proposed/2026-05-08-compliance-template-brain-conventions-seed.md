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
  - PLAN.md#multi-user-evolutionary-design
  - docs/catalogs/privacy-principles-and-data-leak-taxonomy.md
  - docs/design-notes/2026-04-18-full-platform-architecture.md Section 29.2
---

# Compliance Template Brain Conventions Seed

## 1. Recommendation Summary

Seed seven user-authored worked-example pages for compliance template brain
conventions: HIPAA, GDPR, SOX, SOC2, PCI, FERPA, and attorney-privilege.
These pages should be commons artifacts, not platform primitives and not
runtime compliance modes. Their purpose is to teach chatbots how to compose
privacy-aware workflow patterns from existing primitives while preserving the
commons-first rule that real regulated data stays on the user's host.

The smallest useful project change is a proposed design note that fixes the
shape and review gates for the seed pages. Runtime code would be premature:
PLAN.md already rejects pre-baked privacy modes as platform features, while
the privacy taxonomy already names regulated data as private, training-excluded,
and confirm-before-use. The gap is not enforcement code; it is a consistent
authoring convention for high-quality, remixable examples.

## 2. Proposed Seed Shape

Each seed page should be a worked example with the same section skeleton. The
template keeps domain authors in their own vocabulary while making the resulting
pages easy for chatbots to retrieve, compare, and remix.

```yaml
type: compliance_template_brain_convention
domain: hipaa | gdpr | sox | soc2 | pci | ferpa | attorney_privilege
status: proposed | vetted | superseded
author_kind: user-authored
review_gate: opposite-provider privacy review before promotion to vetted
privacy_posture:
  stores_real_regulated_data: false
  example_data_policy: synthetic_or_redacted_only
  default_visibility: concept-public_instance-private
  user_confirmation_required: true
```

Required page sections:

1. **User situation.** A short concrete scenario in user vocabulary.
2. **Public concept pattern.** The reusable workflow shape that belongs in the
   commons, such as intake triage, access review, audit evidence collection, or
   privileged-material handling.
3. **Host-private instance fields.** The real values that must not enter the
   commons: patient identifiers, student records, card data, audit evidence,
   client communications, vendor contracts, access logs, or jurisdiction-specific
   personal data.
4. **Chatbot ask-before-writing points.** The moments where the chatbot must
   ask the user to confirm authority, visibility, or local-only handling before
   it writes or publishes an artifact.
5. **Composition over existing primitives.** The minimal node/gate/review/remix
   composition. This section must not invent a new MCP action or platform flag.
6. **Bad examples.** Two or three near-miss examples that show what not to
   publish, especially real identifiers, quoted privileged text, credentials,
   or vendor-specific confidential details.
7. **Verification checklist.** A review checklist for page promotion.

The seven seed pages should differ in vocabulary and examples, not in platform
contract. HIPAA can discuss care-team workflows, GDPR can discuss data-subject
requests, SOX can discuss financial controls, SOC2 can discuss control evidence,
PCI can discuss payment-card handling, FERPA can discuss education records, and
attorney-privilege can discuss client communication handling. All seven use the
same concept-public / instance-private split.

## 3. Review Gate

Promotion from proposed seed to vetted seed requires a small privacy and
commons review. The reviewer checks the page, not a runtime implementation.

Gate checklist:

- No real regulated data, credentials, privileged material, or third-party
  confidential content appears in the page.
- The page names which parts are public concepts and which parts are host-private
  instance fields.
- The chatbot ask-before-writing points match the privacy taxonomy's T4 posture:
  ask on regulated or legally protected context, and never assume authority.
- The page describes composition using existing primitives and wiki conventions.
- The page avoids legal advice. It can say "ask for confirmation" and "keep this
  data host-private"; it cannot say the workflow makes the user compliant.
- A different provider family reviews before the page is marked `vetted`.

This gate is intentionally editorial. Deterministic lint can catch forbidden
frontmatter drift later, but it cannot decide whether a compliance example is
accurate, jurisdictionally safe, or overclaiming.

## 4. Rejected Alternatives

### Add platform compliance modes

Rejected. PLAN.md explicitly treats privacy and threat-model patterns as
community-built. Shipping `hipaa_mode`, `gdpr_mode`, or similar flags would
freeze a taxonomy in platform code and invite users to over-trust the platform
as a compliance authority.

### Store real examples for realism

Rejected. The examples must be synthetic or redacted. Real regulated data,
audit evidence, payment data, education records, and privileged communications
belong on a host, not in the public commons.

### Make one generic compliance page

Rejected. A single generic page loses the user vocabulary that makes chatbot
composition useful. Seven domain-shaped examples give retrieval enough texture
without creating seven different platform contracts.

### Require attorney or auditor certification before seed publication

Rejected for the seed phase. Professional review may be useful for later
trust labels, but making it a prerequisite would block community authoring.
The seed gate should prevent harmful overclaiming without pretending to certify
compliance.

## 5. Implementation Sketch

Step 0: Add the seven worked examples as proposed wiki pages using the template
above. Keep them user-authored and mark them as examples, not canonical legal
guidance.

Step 1: Run an opposite-family privacy review before promotion to `vetted`.
The reviewer should leave a short note listing any synthetic-data, visibility,
or overclaiming fixes.

Step 2: When retrieval/similarity surfaces ingest the pages, tag them as
`compliance_template_brain_convention` so chatbots can find them while composing
privacy-sensitive branches.

Step 3: If future pages reveal repeated structural gaps, file those gaps as
separate primitive proposals. Do not broaden this seed into runtime work.

## 6. Open Questions

### Q1. Should the seven pages be added now or after a sample authoring pass?

Recommendation: add all seven as proposed pages now, because the value is in
side-by-side examples. Counter-argument: one pilot page might reveal template
problems before six more pages replicate them.

### Q2. What label should signal professional review?

Recommendation: reserve a future `professionally-reviewed` label and do not
use it in this seed. Counter-argument: compliance-adjacent content may benefit
from an explicit "not professionally reviewed" warning in frontmatter.

### Q3. Should examples name real laws and frameworks?

Recommendation: yes, but only as user vocabulary and risk context. The page
must avoid saying Workflow satisfies HIPAA, GDPR, SOX, SOC2, PCI, FERPA, or
attorney-client privilege requirements. Counter-argument: naming regimes at all
may create legal-advice expectations.

### Q4. Should jurisdiction-specific variants exist?

Recommendation: defer variants until users submit real needs. GDPR and
attorney-privilege are especially jurisdiction-sensitive, but the seed should
teach the generic composition pattern first. Counter-argument: vague generic
examples may be less useful than jurisdiction-tagged examples.

### Q5. Where should promotion state live?

Recommendation: frontmatter on each wiki page, with review notes linked from
the page history or a companion review artifact. Counter-argument: central
indexes make promotion state easier to audit across many pages.

## 7. References

- `PLAN.md` Scoping Rules: minimal primitives, community-build, privacy via
  community composition, and commons-first architecture.
- `PLAN.md` Multi-User Evolutionary Design: public concept patterns evolve in
  the commons while instance-private data stays host-resident.
- `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md`: regulated data
  is private, training-excluded, and requires user confirmation.
- `docs/design-notes/2026-04-18-full-platform-architecture.md` Section 29.2:
  transparent privacy reasoning names compliance implications and records
  rationale instead of inferring silently.
