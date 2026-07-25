## ADDED Requirements

### Requirement: The Tier-3 workflow exercises a fresh editable-clone path
The scheduled Tier-3 workflow SHALL shallow-clone the repository into a new `/tmp/tinyassets-fresh` directory, create a Python 3.11 virtual environment there, upgrade pip, and run `pip install -e .`. It MUST also be manually dispatchable and run on the current Ubuntu GitHub-hosted runner.

#### Scenario: The nightly fresh clone starts from repository state
- **WHEN** `tier3-oss-clone-nightly` runs on its daily schedule or through `workflow_dispatch`
- **THEN** it performs `git clone --depth 1 https://github.com/${{ github.repository }} /tmp/tinyassets-fresh`
- **AND** it records the cloned commit with `git rev-parse HEAD`
- **AND** it creates a Python 3.11 virtual environment and installs the clone with `pip install -e .`

### Requirement: The fresh-clone workflow performs the shipped structural checks
The Tier-3 workflow SHALL verify a top-level `tinyassets` import, run `scripts/tier3_smoke.py`, run `scripts/import_graph_smoke.py --verbose`, and run `pytest tests/smoke/ -x --no-header -q` from the installed clone. It MUST fail the job when any one of those steps fails.

#### Scenario: A fresh editable installation is structurally usable
- **WHEN** the clone installs and all Tier-3 checks succeed
- **THEN** the workflow has proven the top-level import plus the current structural import, import-graph, and smoke-test gates in the fresh clone
- **AND** `tier3_smoke.py` has checked the `tinyassets` package, daemon server, universe-server MCP object, bid and catalog modules, and the `fantasy_daemon` domain import

#### Scenario: A structural import regresses
- **WHEN** the top-level import, structural smoke, import-graph smoke, or smoke pytest step fails
- **THEN** the workflow is marked failed
- **AND** later failure-handling steps receive the cloned commit SHA when it can be read

### Requirement: Failed Tier-3 checks emit the current GitHub escalation record
The Tier-3 workflow SHALL emit a GitHub Actions error annotation and create a `tier3-broken` GitHub issue when the fresh-clone job fails. That issue MUST identify the failing commit and run URL and give the current forward-fix debugging order.

#### Scenario: A fresh-clone failure is escalated
- **WHEN** any preceding Tier-3 job step fails
- **THEN** the workflow emits `Tier-3 OSS clone smoke FAILED` as an error
- **AND** it creates or reuses the `tier3-broken` label
- **AND** it opens an issue containing the failing SHA, GitHub Actions run URL, and rerun/fix-forward guidance

### Requirement: The shipped workflow has explicitly bounded coverage
The as-built Tier-3 check MUST NOT be represented as feature-correctness, real-contributor, packaged-installer, multi-platform, or production-service proof. It SHALL currently prove only the Ubuntu/Python-3.11 shallow-clone, editable-install, import, and smoke-test path; `scripts/tier3_smoke.py` additionally inserts the checkout root on `sys.path`, so its own imports are not standalone proof that every import originated exclusively from installed package files.

#### Scenario: A feature works only outside the structural smoke scope
- **WHEN** a feature has not been exercised by the top-level import, `tier3_smoke.py`, import-graph smoke, or `tests/smoke/`
- **THEN** a green Tier-3 workflow does not establish that feature's correctness
- **AND** a separate focused or user-surface acceptance path remains required where applicable

#### Scenario: A reviewer interprets green Tier-3 evidence
- **WHEN** the nightly workflow completes successfully
- **THEN** it is evidence that the current editable install and structural checks passed on the Ubuntu/Python-3.11 GitHub runner
- **AND** it is not evidence of a one-click installer, Windows or macOS installation, or a real external contributor environment
