## ADDED Requirements

### Requirement: Page visibility applies to related-page projections from every surface
The system SHALL apply the existing page-listing visibility predicate to every related-page projection, including branch-originated root-corpus `related_wiki_pages`, before title or body matching, scoring, sorting, cap application, count calculation, or response-item construction. The root-corpus projection SHALL pass the same blank universe context as the root wiki listing surface; it SHALL NOT derive a per-page universe or grant context. Audience and discovery scope SHALL remain relevance controls and MUST NOT substitute for page or universe authority.

#### Scenario: Restricted related page is absent from branch output
- **WHEN** a restricted page mentions a branch or node visible to the caller but the page-listing predicate denies that page
- **THEN** branch get and describe output expose none of its path, title, summary, `matched_via`, body-derived text, or other metadata

#### Scenario: Hidden matches do not affect counts or cap
- **WHEN** visible and restricted pages both match a branch and the visible set exceeds or approaches the related-page cap
- **THEN** filtering occurs before sorting and capping, `truncated_count` is calculated only from visible matches, and hidden pages do not displace visible results

#### Scenario: All matches are restricted
- **WHEN** every page matching a branch is denied by the page-listing predicate
- **THEN** the response retains `related_wiki_pages: []` and `related_wiki_pages_truncated: 0` with no filtered count, denial note, or alternate key set

#### Scenario: Related projection is bounded by wiki listing authority
- **WHEN** the same caller and authority context inspect a fixed wiki corpus through wiki list and a branch related-page projection
- **THEN** every related-page path is contained in the set of paths visible through the wiki listing boundary

#### Scenario: Public pages remain available
- **WHEN** a matching root-corpus page is public
- **THEN** its existing related-page path, title, summary, and match metadata remain available

#### Scenario: Audience classification does not grant visibility
- **WHEN** a restricted matching page is classified as discovery or coordination and the caller requests any audience scope elsewhere
- **THEN** the page remains absent because audience cannot widen the page-listing authority boundary
