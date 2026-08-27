> **Target-only delta.** The first paragraph and the first three scenarios below
> are the as-built `wiki-commons` contract reproduced verbatim, because a
> `MODIFIED` requirement replaces its predecessor wholesale on sync. Everything
> under *Extended for feedback intake* is **target behavior that is not built**.
> This delta exists so feedback filing has exactly one owner instead of two: the
> feedback path extends this typed-filing contract rather than defining a
> parallel filing mechanism. It may not be synced into `openspec/specs/` until
> the extension is implemented with its acceptance evidence.

## MODIFIED Requirements

### Requirement: Typed filings bypass the draft gate with per-kind IDs and dedup
Typed filings routed through `file_bug` SHALL map `kind` to a category directory and ID prefix via `_KIND_ROUTING` (`bug`->BUG, `feature`->FEAT, `design`->DESIGN, `patch_request`->PR), allocate a server-assigned `<PREFIX>-NNN` id from an independent per-kind counter that scans both the kind's `pages/` and `drafts/` directories, and land the page directly in `pages/` bypassing the draft gate. Before filing, the handler SHALL run a per-kind duplicate check that compares the new title-plus-body token set against existing filings of the same kind and, when similarity is at or above the 0.5 threshold, SHALL return a `similar_found` result with candidates instead of minting a new id — unless `force_new` is set. `title`, `component`, and a valid `severity` SHALL be required.

**Extended for feedback intake.** This contract SHALL be the sole owner of typed-filing identity, per-kind identifier allocation, and deduplication for user-submitted feedback; no second filing mechanism, identifier allocator, or duplicate check SHALL be introduced for feedback. `_KIND_ROUTING` SHALL be extended with the feedback categories that have no existing route (`broken_workflow`, `docs`, `question`), each with its own prefix and counter, while feedback categorized as a bug or a feature request SHALL route to the existing BUG and FEAT counters so a user-submitted report and a platform-filed one share one identifier space and one duplicate check. Deduplication for feedback SHALL be the same per-kind title-plus-body similarity check at the same threshold, with no separate dedup identity.

A filing SHALL accept an optional per-invocation `attribute_as` presentation choice of attributed or pseudonymous; that choice SHALL affect presentation only and SHALL NOT remove the authenticated binding retained for abuse control, and SHALL NOT participate in the filing's identity or its duplicate check. A filing SHALL accept optional caller-supplied context, bounded by the publication-authorization requirement in `platform-succession-and-feedback`. For feedback-originated kinds, `component` and `severity` SHALL NOT be required of the submitter: an unspecified `component` SHALL be recorded as unclassified and an unspecified `severity` SHALL be recorded as triage-pending, rather than the filing being refused. The four pre-existing kinds SHALL continue to require `title`, `component`, and a valid `severity`. Filing SHALL require authentication like any other write, SHALL be reachable as an action under `write_page`, and SHALL NOT add an advertised MCP handle.

#### Scenario: kinds use independent id counters and land in pages
- **WHEN** `file_bug` is called with `kind="feature"`
- **THEN** the filing is assigned a `FEAT-NNN` id independent of the BUG counter and is written directly under `pages/` for its kind

#### Scenario: a near-duplicate filing is deflected
- **WHEN** a new filing's title-and-body tokens overlap an existing same-kind filing at or above the 0.5 similarity threshold and `force_new` is not set
- **THEN** the handler returns `similar_found` with the matching candidates and does not mint a new id

#### Scenario: force_new mints a fresh id regardless of similarity
- **WHEN** `file_bug` is called with `force_new=true`
- **THEN** the similarity check is skipped and a new id is always allocated

#### Scenario: feedback reuses the existing kind's counter and dedup
- **WHEN** a user submits feedback categorized as a bug describing a report already filed as `BUG-NNN`
- **THEN** the same per-kind duplicate check deflects it with `similar_found`
- **AND** no separate feedback identifier space or duplicate check is consulted

#### Scenario: a feedback-only category gets its own counter
- **WHEN** a user submits feedback in a category with no pre-existing route
- **THEN** it is assigned an id from that category's own counter and lands directly in `pages/`

#### Scenario: an end user need not classify component or severity
- **WHEN** a feedback filing omits `component` and `severity`
- **THEN** it is accepted with `component` unclassified and `severity` triage-pending
- **AND** a `bug`, `feature`, `design`, or `patch_request` filing omitting them is still refused

#### Scenario: presentation choice does not change filing identity
- **WHEN** the same report is resubmitted with a different `attribute_as` choice
- **THEN** the duplicate check still deflects it as the same filing
- **AND** the authenticated binding is retained regardless of the presentation choice
