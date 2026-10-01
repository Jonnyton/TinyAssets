## MODIFIED Requirements

### Requirement: OKF v0.1 export reads only the curated wiki source set

The OKF exporter SHALL require an existing wiki root, refuse a target directory
inside that source root, and export only sorted Markdown files beneath
`pages/`. It MUST exclude every `soul.md`, source `index.md` and `log.md`, and
Markdown under `drafts/`, `raw/`, and `daemon-wiki`; it SHALL write only to the
target bundle and MUST NOT add an MCP action or mutate the source wiki. It SHALL
be the only OKF writer, and the command-center export (harness design §4.17)
SHALL invoke it through the owner's export door for the folder's `wiki/`; wiki
content outside `pages/` SHALL enter an export only when the owner includes it
in the export's content preview, and no other part of the export SHALL copy
excluded wiki files.

#### Scenario: Curated pages export without private material

- **WHEN** a wiki contains promoted pages plus soul, draft, raw, and daemon-wiki Markdown
- **THEN** only non-reserved promoted page files become concepts and the report lists privacy-excluded files

#### Scenario: Export target cannot be nested in the source wiki

- **WHEN** the requested target resolves inside the source wiki root
- **THEN** export raises `ValueError` before writing the bundle

#### Scenario: A command-center export does not route around the exclusions

- **WHEN** an owner exports a command center whose wiki holds draft and soul files
- **THEN** the folder's `wiki/` holds only the curated concepts, and no brain or workspace copy carries the excluded files unless the owner included them in the preview
