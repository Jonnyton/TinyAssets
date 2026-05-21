---
title: BUG-095 - canon-09 PROV-304 conflicts with Track C local registry
type: bug
status: proposed-fix
source_issue: 943
component: provenance-validator-spec
severity: minor
wiki_source_path: pages/bugs/bug-095-canon-09-6-prov-304-conflicts-with-track-c-local-registry-ev.md
superseded_by: BUG-096
---

# BUG-095 - canon-09 PROV-304 conflicts with Track C local registry

## Problem

canon-09 section 6 assigns `PROV-304` to:

```text
suitability_posterior | evidence_inputs empty
```

The Track C local registry used `PROV-304` for a different validation concern:

```text
suitability_posterior | uncertainty fields missing
```

Those are not interchangeable. `evidence_inputs empty` is a narrow check on a
single required evidence array. `uncertainty fields missing` can refer to a
broader family of missing posterior evidence fields, such as percentile fields
or `n_posterior_samples`.

BUG-096 records the later one-pass audit that found this was part of a wider
registry drift pattern. This BUG-095 artifact therefore keeps the narrow
`PROV-304` decision explicit while deferring multi-code reconciliation to
BUG-096.

## Proposed Additive Amendment

Preserve canon-09 section 6's existing `PROV-304` meaning:

```text
PROV-304 | suitability_posterior | evidence_inputs empty
```

Do not reuse `PROV-304` for missing uncertainty or posterior-support fields.
During the BUG-096 reconciliation slice, assign the local-registry
`uncertainty fields missing` predicate to one or more distinct codes whose
names match the exact fields the local validator checks.

At minimum, the reconciliation must distinguish these cases:

- `evidence_inputs` exists but is empty: emit `PROV-304`.
- required posterior uncertainty fields are absent: emit the new BUG-096
  reconciliation code or codes.
- both failures are present: emit deterministic results according to the
  validator's documented ordering, without making `PROV-304` ambiguous.

## Acceptance

- canon-09 section 6 keeps `PROV-304` reserved for `evidence_inputs empty`.
- Track C fixtures that currently expect `PROV-304` for missing uncertainty
  fields are renamed during the BUG-096 registry reconciliation slice.
- canon-09 section 13 records the additive amendment with date, reason, and
  author.
- BUG-095 closes by reference to the consolidated BUG-096 reconciliation rather
  than by introducing an isolated code mapping here.
