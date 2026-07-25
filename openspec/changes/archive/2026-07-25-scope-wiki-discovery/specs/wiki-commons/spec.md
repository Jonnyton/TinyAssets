## MODIFIED Requirements

### Requirement: Seed taxonomy is a set of defaults, not a closed whitelist
The category list in `_WIKI_CATEGORIES` SHALL be a seed taxonomy of sensible defaults, NOT a closed whitelist. A `write` to a category outside the seed set SHALL be accepted and sanitized into a lowercase slug (a path-traversal-safe path component), and SHALL be rejected only when the sanitized slug is empty. Category discovery for callers that omit a category (promote, supersede) SHALL union the seed categories with any custom category directories found on disk so organically grown categories stay discoverable. Read-side category filtering for search, changed-since, and exact-read ambient recommendations SHALL normalize the supplied value through the same safe slug rule and SHALL compare the exact page or draft category path component without validating against `_WIKI_CATEGORIES`; a valid custom or absent category SHALL remain queryable. For search or changed-since, an explicitly supplied non-empty value that normalizes to an empty slug SHALL return a structured error with no page results rather than becoming an unfiltered query; an exact read SHALL still return the requested body unchanged while its nested ambient feed reports that structured error and contains no recommendation items.

#### Scenario: a custom category is accepted and slugified
- **WHEN** a `write` names a category outside the seed set, such as `Magic Systems`
- **THEN** the page is stored under the sanitized `magic-systems` category
- **AND** the write is not rejected for being off-taxonomy

#### Scenario: an empty-slug category is rejected
- **WHEN** a `write` names a category that sanitizes to an empty slug
- **THEN** the call returns an error listing the seed categories

#### Scenario: omitted-category resolution sees custom directories
- **WHEN** a `promote` omits the category and the matching draft lives in a custom on-disk category directory
- **THEN** category discovery unions the seeds with that directory and finds the draft

#### Scenario: a custom category is filterable
- **WHEN** search, changed-since, or an ambient recommendation filters by a custom category that normalizes to a valid slug
- **THEN** matching pages and drafts in that exact category remain eligible
- **AND** a valid category with no matches returns an empty result rather than an error or widened corpus

#### Scenario: an empty-normalized read filter fails rather than widening
- **WHEN** a caller supplies a non-empty category such as `///` or `!!!` that normalizes to an empty slug
- **THEN** search and changed-since return a structured invalid-category error with no page results
- **AND** an exact read returns its requested body unchanged while its ambient feed reports the error with no recommendation items
- **AND** no surface treats the value as an omitted category

## ADDED Requirements

### Requirement: Default discovery scope separates commons knowledge from coordination history
Wiki search and changed-since feeds SHALL trim scope and resolve an omitted, empty, or whitespace-only value to `discovery`; an exact-read ambient relevance feed SHALL instead resolve that unset scope to the source page's audience class. The core handler SHALL accept only `discovery`, `coordination`, or `all`; any other value SHALL return a structured error naming those values and no page results. Every search, changed-since, and exact-read response with an ambient feed SHALL report the applied scope, and an omitted scope whose audience filtering removes one or more candidates that would otherwise have entered the result set SHALL include a non-fatal scope note explaining intentional coordination/all access for in-process callers. Invalid-scope errors SHALL NOT claim an applied scope, and unchanged list responses SHALL remain unscoped.

Frontmatter `audience: discovery|coordination` SHALL be authoritative. An `audience` key that is absent, empty, or whitespace-only SHALL be treated as unset. A page with an unset audience SHALL classify as coordination when its category is `notes`, `plans`, `bugs`, `feature-requests`, `design-proposals`, or `patch-requests`, and SHALL classify as discovery otherwise, including custom categories and pages with no category component. The audience value SHALL be compared after trimming surrounding whitespace and casefolding; a set value that is still neither `discovery` nor `coordination` SHALL classify as coordination and SHALL NOT fall back to a discovery category.

Audience scope SHALL remain a relevance boundary, not access control. The existing universe ACL gate and page-listing visibility requirements SHALL be evaluated before audience and category filtering, and `all` SHALL NOT bypass them. Exact page-body reads SHALL remain addressable and unfiltered by audience; list behavior SHALL remain unchanged; no page SHALL be moved, rewritten, deleted, or migrated.

#### Scenario: default onboarding search excludes coordination history
- **WHEN** a caller searches a mixed visible corpus without supplying scope
- **THEN** the response contains a non-empty discovery result set
- **AND** untagged notes, plans, bugs, feature requests, design proposals, and patch requests are absent

#### Scenario: changed-since defaults to discovery
- **WHEN** a caller requests changed pages from a mixed visible corpus without supplying scope
- **THEN** the response reports applied scope `discovery`
- **AND** contains discovery-classified results only

#### Scenario: explicit coordination returns preserved history
- **WHEN** an in-process caller searches with `scope=coordination`
- **THEN** the response contains coordination-classified results at their unchanged paths
- **AND** excludes discovery-classified results

#### Scenario: explicit all returns both audience classes
- **WHEN** an in-process caller searches with `scope=all`
- **THEN** the response contains both discovery and coordination results that pass existing authority checks

#### Scenario: invalid scope fails without results
- **WHEN** a caller supplies a scope other than discovery, coordination, or all
- **THEN** the handler returns a structured error naming all three valid scopes
- **AND** returns no page results

#### Scenario: explicit discovery metadata overrides a coordination category
- **WHEN** a page under `pages/plans/` declares `audience: discovery`
- **THEN** the page is eligible for default discovery retrieval

#### Scenario: explicit coordination metadata overrides a discovery category
- **WHEN** a page under `pages/workflows/` declares `audience: coordination`
- **THEN** the page is excluded from default discovery retrieval

#### Scenario: unrecognized audience fails toward coordination
- **WHEN** a page in a discovery category declares a non-empty unsupported audience value
- **THEN** the page classifies as coordination without falling back to its category

#### Scenario: audience is trimmed and case-insensitive
- **WHEN** a page under `pages/plans/` declares a padded, mixed-case `audience: Discovery `
- **THEN** it normalizes to `discovery` and is eligible for default discovery retrieval

#### Scenario: custom and category-less pages default to discovery
- **WHEN** a page with no audience lives in a custom category or directly under the pages or drafts root
- **THEN** it classifies as discovery

#### Scenario: exact coordination read keeps coordination recommendations
- **WHEN** a caller exactly reads a coordination-classified page without supplying scope
- **THEN** the requested page body is returned unchanged
- **AND** its ambient feed applies coordination scope and may return visible coordination siblings

#### Scenario: exact discovery read excludes coordination recommendations
- **WHEN** a caller exactly reads a discovery-classified page without supplying scope
- **THEN** the requested page body is returned unchanged
- **AND** its ambient feed applies discovery scope and excludes coordination siblings

#### Scenario: unrecognized source audience drives coordination ambient scope
- **WHEN** a caller exactly reads a source page with a set but unrecognized audience value and omits scope
- **THEN** the requested page body is returned unchanged
- **AND** its ambient feed applies coordination scope rather than falling back to the source category

#### Scenario: authority denial wins under every audience scope
- **WHEN** an existing universe ACL or page-listing visibility rule denies an ambient, search, or feed candidate
- **THEN** discovery, coordination, and all omit its path, title, excerpt, body, and metadata before relevance scoring

#### Scenario: default filtering is self-auditing
- **WHEN** omitted scope filters one or more otherwise-visible candidates
- **THEN** the response reports its applied scope and a non-fatal scope note
- **AND** an explicit scope response reports its applied scope without claiming privacy

#### Scenario: list remains an unscoped inspection surface
- **WHEN** an in-process caller lists the wiki
- **THEN** the existing visibility-filtered page and draft listing behavior is unchanged

#### Scenario: concurrent defaults are request-local and deterministic
- **WHEN** 256 default discovery searches execute concurrently against a fixed mixed corpus
- **THEN** every response is byte-identical to the non-empty single-threaded reference and excludes coordination paths
- **AND** the proof claims only request-local single-process determinism while the full-platform §14 load suite remains open
