## ADDED Requirements

### Requirement: User-facing discovery excludes coordination history by default

Wiki search, changed-since feeds, and ambient relevance results SHALL default to `scope=discovery`. Coordination pages SHALL remain stored, directly readable by path, and discoverable through explicit `scope=coordination` or `scope=all`.

#### Scenario: onboarding search does not return coordination logs
- **WHEN** a caller searches with no explicit scope
- **THEN** results contain discovery-classified pages only
- **AND** agent checker records, patch requests, bugs, and internal plans are absent

#### Scenario: an operator can inspect preserved coordination history
- **WHEN** a caller searches with `scope=coordination`
- **THEN** coordination-classified pages are returned
- **AND** no page has been moved or deleted

#### Scenario: exact historical read remains stable
- **WHEN** a caller reads the known path of a coordination page
- **THEN** the page content is returned at the same path
- **AND** ambient recommendations obey the requested scope

### Requirement: Explicit audience metadata overrides legacy classification

Frontmatter `audience: discovery|coordination` SHALL be authoritative. Without it, scratch-heavy legacy categories (`notes`, `plans`, `bugs`, `patch-requests`, `design-proposals`) SHALL classify as coordination and other categories SHALL classify as discovery.

#### Scenario: a user project plan is promoted into discovery
- **WHEN** a page under `pages/plans/` declares `audience: discovery`
- **THEN** default discovery search may return it

#### Scenario: a platform note stays internal
- **WHEN** an untagged page is under `pages/notes/`
- **THEN** default discovery search excludes it

### Requirement: Category filters are enforced

The advertised `category` parameter SHALL restrict search results to that exact normalized page/draft category after scope filtering.

#### Scenario: workflows-only search
- **WHEN** a caller searches with `category=workflows`
- **THEN** every returned result path is under `pages/workflows/` or `drafts/workflows/`

### Requirement: Invalid scope fails explicitly

Unknown scope values SHALL return a structured error listing `discovery`, `coordination`, and `all`; the server SHALL NOT silently fall back to an unfiltered search.

#### Scenario: typo does not expose the full corpus
- **WHEN** a caller passes `scope=discover`
- **THEN** the call returns an invalid-scope error
- **AND** returns no page results
