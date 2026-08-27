## MODIFIED Requirements

### Requirement: Draft-then-promote gate for freeform pages
A freeform `write` to a slug that has no already-promoted page SHALL land in `drafts/<category>/` and instruct the caller to call `promote`; a `write` to a slug whose `pages/<category>/<slug>.md` already exists SHALL update that promoted page in place instead of re-drafting, **except** where that page's frontmatter marks it as an immutable content-addressed entry. `promote` SHALL move a draft into `pages/`, run promotion lint unless `skip_lint` is set (blocking on lint issues), remove the source draft, and update the index. As-built limitation: the draft gate applies to freeform `write` only; typed filings (see the typed-filing requirement) and first-party canon writes bypass it.

A freeform `write` targeting a slug whose promoted page is marked an immutable content-addressed entry SHALL be refused, with a response that names the immutability and instructs the caller to mint a new version at its own content-addressed slug; the existing page's body, frontmatter, and index entry SHALL be left unchanged. A content-addressed slug alone SHALL NOT be relied on to prevent the collision — the refusal SHALL be enforced on the write path itself, because a later write to the same slug is otherwise an in-place overwrite. This exception SHALL apply to the immutable-entry content class only: every other freeform write keeps the in-place overwrite behavior unchanged, and the exception SHALL NOT be read as a general pre-publication review gate, an ownership restriction, or a new write path.

#### Scenario: new content drafts, not publishes
- **WHEN** a `write` targets a slug with no existing promoted page
- **THEN** the content is stored under `drafts/<category>/` with a status indicating it must be promoted

#### Scenario: writing an existing promoted page updates in place
- **WHEN** a `write` targets a slug whose promoted `pages/<category>/<slug>.md` already exists and whose frontmatter does not mark it an immutable content-addressed entry
- **THEN** the promoted page is overwritten in place and no new draft is created

#### Scenario: writing an existing immutable entry is refused
- **WHEN** a `write` targets a slug whose promoted page is marked an immutable content-addressed entry
- **THEN** the write is refused and the response instructs the caller to mint a new version at its own content-addressed slug
- **AND** the existing page's body, frontmatter, and index entry are unchanged, and no draft is created

#### Scenario: promote moves draft to pages
- **WHEN** `promote` is called for a draft that passes promotion lint
- **THEN** the file is moved from `drafts/` to `pages/`, the draft is removed, and the index is updated
