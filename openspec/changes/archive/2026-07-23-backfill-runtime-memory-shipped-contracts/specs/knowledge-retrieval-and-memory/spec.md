## ADDED Requirements

### Requirement: OKF v0.1 export reads only the curated wiki source set

The OKF exporter SHALL require an existing wiki root, refuse a target directory
inside that source root, and export only sorted Markdown files beneath
`pages/`. It MUST exclude every `soul.md`, source `index.md` and `log.md`, and
Markdown under `drafts/`, `raw/`, and `daemon-wiki`; it SHALL write only to the
target bundle and MUST NOT add an MCP action or mutate the source wiki.

#### Scenario: Curated pages export without private material

- **WHEN** a wiki contains promoted pages plus soul, draft, raw, and daemon-wiki Markdown
- **THEN** only non-reserved promoted page files become concepts and the report lists privacy-excluded files

#### Scenario: Export target cannot be nested in the source wiki

- **WHEN** the requested target resolves inside the source wiki root
- **THEN** export raises `ValueError` before writing the bundle

### Requirement: OKF export normalizes concepts, links, reserved files, and evidence

Each exported concept SHALL have `type`, `title`, `timestamp`, and
`workflow_original_path` metadata, using the current frontmatter, heading,
slug, or file-mtime fallbacks and preserving non-empty top-level source fields
recognized by the lightweight parser under `workflow_` keys; this is not
lossless YAML round-tripping. The exporter MUST convert resolvable wikilinks to
absolute bundle links, render unresolved wikilinks as plain labels while
reporting them, write root `index.md` with `okf_version: "0.1"`, write dated
root `log.md`, and return a conformance report with concepts, exclusions,
unresolved links, reserved-file validation, issues, and counts. `conformant`
SHALL be the exporter's local structural flag only: it validates generated
reserved-file shapes and parseable concept frontmatter with non-empty `type`,
not complete upstream OKF conformance or canonical-store authority. Unresolved
links, privacy exclusions, and source pages named `index.md` or `log.md` SHALL
be reported but SHALL NOT independently make `conformant` false.

#### Scenario: Metadata and links are normalized into the bundle

- **WHEN** a promoted page has partial frontmatter and links to another exported page
- **THEN** the concept receives required fallback metadata, recognized non-empty top-level source fields are retained under `workflow_` keys, and the link becomes an absolute bundle link

#### Scenario: Unresolved links remain readable and evidenced

- **WHEN** a promoted page links to a target absent from the export set
- **THEN** the rendered body contains the readable label without a link and the report identifies the source and unresolved target

#### Scenario: Bundle reserved files are regenerated

- **WHEN** export completes with zero or more concepts
- **THEN** root `index.md` and `log.md` are written in the current OKF v0.1 shapes and their validation results appear in the report

#### Scenario: Reserved source-name issue is non-fatal

- **WHEN** a promoted source page itself is named `index.md` or `log.md` and no other conformance issue exists
- **THEN** that source page is omitted and reported as an issue while the report remains conformant

#### Scenario: Local conformance is deliberately narrow

- **WHEN** a bundle has valid generated reserved files and parseable concept frontmatter with non-empty types but also has unresolved links or privacy exclusions
- **THEN** the local `conformant` flag remains true and does not claim complete upstream OKF or canonical-store conformance
