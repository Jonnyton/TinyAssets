# Regulated-Industry Compliance Architecture Implications

**Archival status (2026-07-23):** Historical research evidence, current only as
of the checkpoints recorded below. Re-check every code, spec, legal, standards,
privacy, and operational prescription against fresh authoritative sources and
current `origin/main` before using it. The Claude verdict remains **ADAPT**, not
approval, legal advice, certification, or build authority.

**Status:** Codex initial research and architecture implications; no legal
determination, certification claim, OpenSpec, or runtime build is authorized.
Law and standards are jurisdiction-, role-, version-, contract-, configuration-,
and fact-dependent. Sources were checked against the current official materials
linked below on 2026-07-21. Qualified counsel, security/compliance owners, and
where applicable an independent assessor remain required. The required Claude
review returned **ADAPT**, independently reconfirmed the highest-risk legal
claims, and its corrections are folded below. This remains planning research,
not implementation or compliance authority. The host-owned private-data/PLAN
decision, consent-path triage, and provider-authority prerequisites remain open.

## Executive answer

TinyAssets should not build a separate “HIPAA edition,” “finance edition,” or
“government edition.” It should build a common governed-execution substrate and
bind **versioned compliance profiles** to organization universes, connectors,
data classes, and execution routes.

A profile is not a compliance badge. It is an executable and reviewable package
of:

- applicability facts and customer assertions;
- legal/standard/control references with jurisdiction, version, and effective
  dates;
- data classifications, allowed purposes, residency/retention rules, roles,
  approvals, and prohibited routes;
- contract and vendor prerequisites such as BAAs or data-processing agreements;
- machine-enforced controls and human/organizational obligations;
- evidence queries, tests, reports, exceptions, compensating controls, and
  renewal/review dates; and
- a deployment eligibility predicate for storage, connectors, models, compute,
  and market hosts.

The same primitives can serve healthcare, finance, government, education,
privacy, payments, and AI governance. Their obligation mappings differ. The
platform may truthfully say “this deployment enforces profile version X and
produced evidence Y”; it must not say “HIPAA compliant,” “FedRAMP authorized,”
“SOC 2 certified,” or equivalent merely because toggles exist.

One architecture decision remains explicitly host-owned. Canonical PLAN says
private content never resides on the platform; a host-ratified but unreconciled
direction in `docs/specs/2026-06-10-tiny-first-principles-spec.md` section 11
instead makes permissioned-cloud-private the compliance-grade north star and
states that it supersedes commons-first absolutism. Live `daemon_memory_capture`
already writes `host_private`/`sensitivity_tier` records into platform-root
`daemon_brain.db`, violating canonical PLAN as currently written. Compliance
work cannot use that contradiction as implicit permission: PLAN must identify
the operative private-data model and the live storage path must conform to it.

## Do not collapse unlike authorities

| Kind | Examples | What it means for TinyAssets |
|---|---|---|
| Law/regulation | HIPAA/HITECH, GLBA, FERPA, GDPR, EU AI Act | Applicability and duties depend on role, data, activity, jurisdiction, and current law |
| Government authorization program | FedRAMP | A specific cloud service offering and boundary undergoes authorization/continuous monitoring; code features alone are not authorization |
| Industry standard | PCI DSS, ISO/IEC 27001 | A scoped standard with assessment/conformity rules; version and system boundary matter |
| Audit/reporting framework | SOC 2 | An independent examination/report over defined trust criteria, period, controls, and entity boundary--not a product switch |
| Voluntary risk framework | NIST CSF, Privacy Framework, AI RMF | Useful common control/outcome vocabulary; generally not itself law or certification |
| Customer/internal policy | retention schedule, model allowlist, segregation of duties | May be stricter than law and must remain versioned, enforceable, and auditable |

This typed distinction belongs in the product. A `StandardReference` cannot be
interchangeable with a `Certification`, `ContractRequirement`,
`CustomerPolicy`, or `EvidenceAssertion`.

## Shared architecture

```text
Organization universe + data inventory + declared processing purposes
                              |
                              v
Applicability assessment (human-owned, evidence-backed)
                              |
                              v
Versioned ComplianceProfile bindings
  controls + contracts + eligible routes + retention + evidence tests
                              |
                              v
Policy decision at admission, retrieval, model call, host lease, and effect
                              |
             allow | require approval | transform | hold | deny
                              |
                              v
Owner-authorized compute/model route or accepted eligible market offer
                              |
                              v
Immutable receipts + evidence artifacts + SIEM/GRC export + review clock
```

### Core records

| Record | Minimum content |
|---|---|
| `DataClass` | sensitivity, regulated categories, source, subject type, allowed purposes, default handling |
| `ProcessingPurpose` | documented use, lawful/contractual basis reference, approved actors, expiry/review |
| `ComplianceProfile` | immutable version, authority type, jurisdiction/industry, source versions/effective dates |
| `ControlRequirement` | normalized control objective, machine/human/contract/assessor owner, severity |
| `PolicyBinding` | organization/universe/data/connector/workload scope, parameters, precedence |
| `VendorRouteEligibility` | provider/service/region/model/host, contract/attestation evidence, allowed data/use |
| `ContractEvidence` | BAA/DPA/SLA/terms/subprocessor approval reference and dates; sensitive contract stored privately |
| `ControlEvidence` | test/query/config/log/receipt/attestation result, freshness, environment, artifact hash |
| `Exception` | scope, justification, approvers, compensating control, expiry, revalidation |
| `IncidentCase` | detection, containment, affected data/subjects/vendors, clock, decisions, notifications |
| `SubjectRequest` | access/correction/export/restriction/deletion workflow with holds and identity proof |
| `RetentionDisposition` | source, copy graph, retention/hold precedence, deletion proof/exception |

Profiles compose through explicit precedence. A healthcare customer in the EU
may bind HIPAA, GDPR, an internal clinical-safety policy, and ISO controls at
once. Composition computes the strictest compatible outcome; contradictory
requirements produce a human-owned conflict, not silent last-write-wins.

Profile names state their real scope--for example, `HIPAA Security Rule evidence
profile`, `FINRA communications-records profile`, or `FERPA school-official
profile`--never “HIPAA mode.” Pack metadata includes publisher, license,
integrity hash/signature, source versions/effective/as-of dates, applicability
questions, superseded versions, dependencies, system boundary, shared-
responsibility allocation, and review cadence.

Evidence posture is deliberately non-marketing:

```text
not_assessed | evidence_missing | implemented_unverified
| verified_on:<date> | gap | not_applicable:<rationale>
| exception_approved:<expiry>
```

`compliant` and `certified` are not machine-generated states. External
attestations are stored with issuer, exact scope, standard/version, validity,
artifact hash, and caveats; TinyAssets never mints them.

Keep three artifacts distinct:

- a **policy pack** supplies enforceable decisions and obligations;
- an **evidence pack** collects scoped, freshness-stamped artifacts and
  attestations; and
- a **conformance pack** evaluates evidence against a named profile.

TinyAssets already has promising conformance/gate-attestation ideas, but those
are readiness evidence, not runtime authorization. A regulated write can carry
an `audit_required` obligation and fail closed if the same transaction cannot
write its audit outbox; a later best-effort JSON append is not sufficient.

## Control primitives shared across industries

### 1. Inventory, classification, and purpose

Every artifact, prompt/context bundle, embedding/index entry, model output,
trace, backup, connector copy, and training/tuning dataset needs a data owner,
organization/universe, classification, provenance, purpose, retention class,
and permitted route class. Derived data does not automatically lose the source
classification. Embeddings and model outputs can still reveal sensitive data.

The platform must support data minimization and selective retrieval rather than
copying whole Slack/Teams/workspace histories into a “brain.” A policy decision
occurs before retrieval and again before an external model/host call because
the eligible route can depend on the actual data selected.

### 2. Identity, least privilege, and separation of duties

Use organization membership, SSO/SCIM lifecycle, least-privilege roles,
resource/action/data attributes, step-up approval, session/device assurance
where available, immediate deprovisioning, and time-bounded break-glass access.
High-risk profile/policy, connector, export, market, key, and effect changes need
four-eyes approval where the profile requires it.

Service identities and autonomous agents are principals with owners, grants,
budgets, expiry, and review. They are never invisible extensions of the founder
account.

### 3. Cryptography, keys, and secrets

Profiles declare transport/storage encryption, approved key custody, rotation,
backup/recovery, secret isolation, and whether customer-managed keys or a
private enclave are required. Encryption is only one safeguard. HHS explicitly
states that a cloud provider maintaining encrypted ePHI can still be a business
associate even without the decryption key; no-view encryption does not erase
contractual, integrity, availability, or breach obligations.

### 4. Data location and route eligibility

Admission computes an eligibility predicate over:

```text
data_class + purpose + organization policy + jurisdiction/region
+ provider/service/model/host identity + contract/attestation status
+ subprocessors + network/tool permissions + retention/logging behavior
```

BYOC/market is necessary but not sufficient. A user's chosen host may still be
ineligible for ePHI, cardholder data, export-controlled material, student
records, or EU personal data. Market offers therefore advertise verifiable
capability, region, security/contract profile, subprocessors, model/data-use
terms, and evidence freshness. Matching never treats seller self-assertion as
certification.

### 5. Audit, evidence, and observability

Receipts bind actor/service identity, organization/universe, action, input/output
references and hashes, policy/profile versions, decision reason, connector,
model/provider, compute/model authority owner, market offer, region, budget,
approvals, lease epoch, result, and incident/reconciliation state.

Sensitive content is not sprayed into logs. Audit evidence uses bounded fields,
private artifact references, redaction, integrity protection, retention, export,
and independent access controls. Customers can send organization audit events
to their SIEM/GRC system.

### 6. Retention, legal hold, deletion, and portability

Maintain a copy graph: authoritative artifact, Slack/Teams copy, connector cache,
embedding/index, model/provider trace, executor scratch, backup, export, and
settlement/audit receipt. A deletion workflow evaluates legal hold, minimum
retention, contractual need, user/subject rights, security evidence, and system
capability for every copy. It reports completed, retained-with-reason,
unreachable, and externally-owned copies truthfully.

Legal hold overrides normal deletion only within its documented scope. A hold,
retention schedule, or source-system deletion is never assumed to propagate
automatically across systems.

### 7. Vendor, subprocessor, and contract management

Profiles require approved service offerings and contracts, not merely brand
names. One vendor may have commercial, healthcare, government, or regional
offerings with different boundaries. Store service-offering/version/region and
contract evidence; monitor expiry, subprocessor change, lost authorization,
security advisories, and configuration drift. An accepted market host becomes
a service provider/subprocessor according to the applicable facts--the market
does not make contractual duties disappear.

### 8. Incident and breach workflow

Provide detection, containment, evidence preservation, route/key/connector
revocation, affected-data and affected-vendor reconstruction, risk assessment,
notification clocks, customer/counsel decisions, regulator/subject delivery,
postmortem, and control remediation. Deadlines and reportability are profile
inputs owned by qualified humans; the system tracks clocks and evidence but
does not make unsupported legal conclusions.

## Initial profile families

### HIPAA / HITECH healthcare profile

Scope only where an organization is a covered entity or business associate and
TinyAssets or a connected provider creates, receives, maintains, or transmits
PHI/ePHI on its behalf. HHS says a cloud provider doing so is generally a
business associate even when data is encrypted and it lacks the key. A
HIPAA-compliant BAA is required with that provider, plus risk analysis/risk
management and applicable Privacy, Security, and Breach Notification duties.
HHS does not certify or endorse “HIPAA-compliant” cloud products.

Profile implications:

- ePHI classification and minimum-necessary/purpose restrictions;
- BAAs and approved subcontractor chain for every storage, model, compute,
  connector, and market service that handles ePHI;
- administrative, physical, and technical safeguard evidence;
- unique identities, access control, audit controls, integrity, authentication,
  transmission security, contingency/availability, backup/recovery, and risk
  analysis evidence;
- patient/individual access, amendment, and disclosure-accounting support where
  the customer's role/workflow requires it;
- breach workflow and contract-specific notification terms; and
- de-identification only when the approved HIPAA method and evidence are
  satisfied--not because a model claims text “looks anonymous.”

Slack states that it can be configured for HIPAA use subject to its requirements;
that does not make every workspace, plan, app, integration, retention setting,
or TinyAssets route eligible. Each actual service offering/configuration and BAA
must be validated.

### Financial-services profile

The FTC Safeguards Rule requires covered financial institutions to maintain an
information security program with administrative, technical, and physical
safeguards and to oversee service providers. Its applicability is entity and
information specific. Add risk-assessment ownership, qualified-individual and
board/reporting evidence where applicable, encryption/MFA/access controls,
secure development/change, monitoring/testing, provider oversight, incident
response, and current breach-reporting workflow.

Separate overlays may cover securities/communications retention, banking
regulators, state rules, or payment data. Do not call the whole profile “GLBA”
if only one FTC-regulated subset was mapped.

Broker-dealer/FINRA overlays need immutable or reconstructable record history,
usable export, communications-capture policy, supervisory review, written
procedures, holds, and medium/content-specific retention. Slack or Teams audit
feeds corroborate activity; they do not replace the organization's books and
records or prove every message was captured.

### Payment-card profile

Prefer scope reduction: never ingest/store/process cardholder data if a
tokenized payment provider can handle it. If in scope, bind the current PCI DSS
version (PCI SSC identifies v4.0.1 as the active limited revision), precise
cardholder-data environment, segmentation evidence, approved scans/tests,
assessment type, and service-provider responsibilities. A generic encryption
toggle or SOC report does not establish PCI compliance.

### US government profile

FedRAMP applies to a particular cloud service offering and authorization
boundary and uses ongoing monitoring/agency authorization processes. A
TinyAssets policy pack can map required controls, configuration, evidence,
POA&M, change monitoring, region/offer eligibility, and agency responsibilities;
it cannot confer FedRAMP authorization. Government cloud variants and impact
levels are separate offerings, not a `fedramp=true` provider property.

Use NIST SP 800-53/CSF mappings as reusable control vocabulary where selected,
while preserving the exact baseline/tailoring and authorization source.
Collaboration content can also be a federal record: retention is scheduled by
record series/content and office, not one duration flag per universe.

### Education profile

FERPA applicability depends on education records and the institution/provider
relationship. US Department of Education guidance says providers relying on
the school-official exception operate under the institution's direct control,
perform an institutional service/function, use records only for authorized
purposes, and avoid unauthorized redisclosure. Capture institution authority,
legitimate educational interest, contract restrictions, parent/eligible-student
rights workflows, directory-information choices, deletion/return, and state or
child-privacy overlays separately.

### General privacy / GDPR profile

Bind controller/processor roles, processing purpose and lawful-basis evidence,
data minimization, transparency, rights requests, retention, security, breach,
processor/subprocessor contracts, international transfer mechanism, region,
and data-protection-impact assessment triggers. Do not model consent as the
universal basis or deletion as an unconditional one-click action; legal bases,
rights, exceptions, and holds differ.

### AI governance profile

The EU AI Act is risk- and role-based; its official regulation text must be
mapped by system/use case and effective provisions, not by calling every LLM
“high risk.” NIST AI RMF is a voluntary risk-management framework, useful for
govern/map/measure/manage evidence but not legal certification.

Profile primitives include use-case inventory, prohibited-use screening,
provider/deployer role, intended purpose, affected people, training/data
provenance, evaluation, robustness/security, human oversight, transparency,
logging, incident/monitoring, change classification, and model/version lineage.
The same model can have different obligations in different uses; bind policy to
the deployed workflow/use case, not only the model name.

### Cross-sector security baseline

ISO/IEC 27001:2022 defines requirements for an information security management
system; NIST CSF/Privacy Framework supply risk/outcome structure. TinyAssets can
generate evidence and control mappings for an organization's ISMS. Certification
or audit remains scoped to an organization/system and performed under the
relevant assessment scheme.

## Policy-pack design

```yaml
profile_id: healthcare-us-hipaa
version: 2026-07-21-research-draft
authority:
  kind: law_regulation
  jurisdiction: US
  sources: [versioned official references]
applicability:
  required_facts: [organization_role, data_is_phi, service_functions]
  decision_owner: customer_compliance_owner
controls:
  - objective: authorized_route_for_ephi
    enforcement: machine
    evidence: route_receipt_query
  - objective: current_baa_for_every_handler
    enforcement: contract_plus_machine_gate
    evidence: contract_registry_query
  - objective: risk_analysis
    enforcement: human_process
    evidence: approved_assessment_artifact
route_policy:
  require: [approved_service_offering, region, contract_chain, fresh_evidence]
exceptions:
  approval: [privacy_owner, security_owner]
  max_duration: bounded
```

This is illustrative, not a claim that three controls satisfy HIPAA. The
important interface is typed authority, applicability, enforcement kind,
evidence, route eligibility, exceptions, and freshness.

## Evidence and claims ladder

TinyAssets should expose claims at the narrowest defensible level:

1. **Control available:** the software implements a capability.
2. **Control configured:** a named deployment has a versioned setting.
3. **Control operating evidence:** a test/query/log supports operation for a
   stated period/environment.
4. **Profile conformance:** all machine-testable profile requirements passed and
   human/contract evidence is present; exceptions are explicit.
5. **Customer compliance determination:** customer/counsel owns the conclusion.
6. **Independent assessment/certification/authorization:** only the relevant
   assessor or authority can issue it for the stated scope.

UI, APIs, market listings, and marketing language must not jump levels.

## Current TinyAssets implications

Useful existing primitives:

- universe visibility/ACL and authenticated action gating;
- immutable-ish nodes/graphs, CAS/version concepts, receipts/idempotency intent;
- credential vault direction, provider-neutral routing, BYOC/market model;
- goals/gates/evaluation and reviewable branch history; and
- private/public universe separation and commons provenance.

Blocking gaps:

- no organization/membership/SCIM/enterprise role substrate;
- current public storage/runtime cannot provide horizontally scalable,
  organization-scoped transactional authority or complete evidence;
- owner/market-only execution authority conflicts with canonical provider
  fallback and is not yet proven across every graph/provider path;
- no first-class data classification/purpose/residency/retention/hold/copy graph;
- no contract/subprocessor/service-offering registry or route eligibility proof;
- no organization audit schema/SIEM export/control-evidence freshness engine;
- no incident/subject-rights/deletion orchestration;
- no signed/versioned policy-pack schema, precedence, exception, or upgrade
  semantics; and
- no policy/evidence/conformance-pack type separation; current conformance
  evaluation must not be treated as runtime enforcement;
- current boundary-layer exactly-once wording exceeds what arbitrary external
  providers can guarantee without idempotency/status reconciliation.

The execution dependency is concrete on fresh `origin/main`: PR #1546 closed
the ambient-host-subscription inheritance half, while **R2-1a** (strict
`allowed_providers` selection) and **R2-1b** (race-safe provider and credential-
class receipts) remain pending. No regulated profile may treat owner/market-only
routing as proven until both land and the graph path is covered.

## Required tests

- policy composition precedence and explicit conflict on incompatible profiles;
- tenant/data-class/purpose isolation under forged IDs and adversarial retrieval;
- revocation at every durable boundary and immediately before external effect;
- route refusal for missing/expired contract, wrong region, disallowed model,
  unapproved subprocessor, stale evidence, or market self-assertion;
- no sensitive content in logs/queues/traces/error messages;
- retention versus hold versus subject request across the complete copy graph;
- key/credential rotation, backup restore, executor loss, and incident evidence;
- malicious policy pack, downgrade, rollback, signature, and source-version
  freshness tests;
- organization export proves actor/action/policy/provider/authority lineage;
- rendered Slack/Teams/chatbot conversations for real regulated workflows; and
- independent assessor/legal review of mappings before any compliance claim.

## Recommended sequence

1. Build organization identity/membership and the execution authority bundle
   before regulated profiles; depend explicitly on R2-1a/R2-1b and graph-path
   isolation proof.
2. Define a generic data-class/purpose/policy-decision/receipt contract in an
   OpenSpec change, with deny/hold as first-class results.
3. Define signed immutable compliance profiles, typed authority sources,
   precedence, human/contract controls, exceptions, and freshness.
4. Implement copy graph, retention/hold/deletion, contract/service-offering
   registry, route eligibility, audit/SIEM export, and incident cases.
5. Pilot one narrow healthcare workflow with no production ePHI, qualified
   counsel/security owners, and deterministic test data; independently review
   the mapping.
6. Add finance, government, education, privacy, payment, and AI overlays from
   their current primary authorities rather than cloning the HIPAA pack.
7. Only pursue named certification/authorization after the production service
   boundary, operations, contracts, evidence period, and assessor route exist.
8. Reconcile canonical PLAN with the host-ratified permissioned-cloud-private
   direction and repair the already-live platform-private memory contradiction.

## Source provenance

Current official primary references:

- HHS HIPAA Security Rule and guidance:
  <https://www.hhs.gov/hipaa/for-professionals/security/index.html> and
  <https://www.hhs.gov/hipaa/for-professionals/security/guidance/index.html>
- HHS HIPAA cloud and business-associate guidance:
  <https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html>
  and <https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/index.html>
- FTC Gramm-Leach-Bliley Act and Safeguards Rule:
  <https://www.ftc.gov/business-guidance/privacy-security/gramm-leach-bliley-act>,
  <https://www.ftc.gov/legal-library/browse/rules/safeguards-rule>, and
  <https://www.ftc.gov/business-guidance/resources/ftc-safeguards-rule-what-your-business-needs-know>
- PCI Security Standards Council on PCI DSS v4.0.1:
  <https://blog.pcisecuritystandards.org/just-published-pci-dss-v4-0-1>
- FedRAMP program and continuous monitoring:
  <https://www.fedramp.gov/rfcs/0026/> and
  <https://www.fedramp.gov/legacy/playbook/csp/continuous-monitoring/overview/>
- US Department of Education FERPA/vendor guidance:
  <https://studentprivacy.ed.gov/ferpa> and
  <https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Vendor%20FAQ.pdf>
- EU GDPR and AI Act official texts:
  <https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng> and
  <https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng>
- NIST Privacy Framework and AI RMF:
  <https://www.nist.gov/privacy-framework> and
  <https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf>
- NIST SP 800-53 and NARA collaboration-platform records guidance:
  <https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final> and
  <https://www.archives.gov/records-mgmt/bulletins/2023/2023-04>
- SEC electronic recordkeeping and FINRA books-and-records rules:
  <https://www.sec.gov/investment/amendments-electronic-recordkeeping-requirements-broker-dealers>
  and <https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511>
- FTC COPPA guidance and California Privacy Protection Agency FAQ:
  <https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions>
  and <https://cppa.ca.gov/faq>
- ISO/IEC 42001 AI management-system overview:
  <https://www.iso.org/standard/42001.html>
- TinyAssets host-ratified permissioned-private/compliance direction:
  `docs/specs/2026-06-10-tiny-first-principles-spec.md` sections 11 and 11.3.
- ISO/IEC 27001:2022 overview:
  <https://www.iso.org/standard/27001>
- Slack compliance/HIPAA configuration context:
  <https://slack.com/trust/compliance> and
  <https://slack.com/help/articles/360020685594-Slack-and-HIPAA>
