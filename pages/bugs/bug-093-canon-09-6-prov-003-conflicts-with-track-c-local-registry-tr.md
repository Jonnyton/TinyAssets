---
title: BUG-093 - canon-09 PROV-003 conflicts with Track C local registry
type: bug
status: proposed-fix
source_issue: 941
component: provenance-validator-spec
severity: minor
wiki_source_path: pages/bugs/bug-093-canon-09-6-prov-003-conflicts-with-track-c-local-registry-tr.md
---

# BUG-093 - canon-09 PROV-003 conflicts with Track C local registry

## Problem

canon-09 section 6's `PROV-003` case is ambiguous because it combines two
different validation concerns:

- `transformation_lineage` is empty.
- `record_type` is invalid for the Track C local registry.

Track C's local registry contract treats an unknown or unsupported
`record_type` as a structurally invalid registry record. That means a fixture
with both an empty lineage and an invalid `record_type` cannot prove the
empty-lineage rule; it proves, or should prove, `invalid_record_type` first.

## Additive Amendment

Amend canon-09 section 6 so `PROV-003` is interpreted as follows:

1. An empty `transformation_lineage` is valid only for a root/source
   provenance record whose `record_type` is valid in the local registry.
2. If `record_type` is invalid, the expected validator result is
   `invalid_record_type`, regardless of the value of `transformation_lineage`.
3. Any test whose purpose is to exercise empty lineage must use a valid
   root/source `record_type` and must not also rely on the invalid-record-type
   fixture.

This is additive: it does not remove the empty-lineage case and does not relax
the local registry. It separates fixture intent so validator implementations
can report deterministic, contract-aligned failures.

## Acceptance

- canon-09 section 6 no longer presents `PROV-003` as both an empty-lineage
  fixture and an invalid-record-type fixture.
- Track C local registry validators continue to reject unsupported
  `record_type` values.
- Empty `transformation_lineage` coverage uses a valid local-registry
  `record_type` when the record is intended to represent a root/source
  provenance item.
