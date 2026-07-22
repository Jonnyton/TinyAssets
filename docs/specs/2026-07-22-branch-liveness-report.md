# Spec: Squash-aware branch liveness report

## Objective

Expose a read-only answer to “is this remote branch dead?” without treating
commit ancestry as merge evidence. The report reuses
`git_squash_merge.is_merged_into`, identifies stack containment, and reserves
`STRANDED` for branches proven to have no open PR, no equivalent change on
main, and no containing remote ref.

## Tech stack and commands

- Python 3.11+ and the standard library only.
- Test: `python -m pytest -q tests/test_branch_liveness.py tests/test_branch_janitor.py`
- Lint: `ruff check scripts/branch_janitor.py tests/test_branch_liveness.py`
- Human report: `python scripts/branch_janitor.py --liveness`
- JSON report: `python scripts/branch_janitor.py --liveness --json`
- Gate: `python scripts/branch_janitor.py --liveness --exit-code`

## Project structure and interface

- Extend `scripts/branch_janitor.py`; do not add a second classifier.
- Keep squash detection in `scripts/git_squash_merge.py` unchanged.
- Add regression coverage in `tests/test_branch_liveness.py`.
- The liveness mode emits one of `OPEN-PR`, `MERGED`, `CONTAINED`,
  `STRANDED`, or `UNDETERMINED` for each non-protected remote branch.
- JSON includes PR-attribution availability and report-level errors.

## Code style

Use frozen dataclasses for report records and small pure classification/render
functions. External command output is validated at its boundary. Existing
janitor deletion behavior and output remain unchanged outside `--liveness`.

## Testing strategy

Mock git and `gh`; tests make no network calls. The squash regression exercises
the real `is_merged_into` helper with mocked git results. A mutation proof
replaces it with an ancestor-only stub and demonstrates that test failing.

## Boundaries

- Always: fail closed to `UNDETERMINED` on git ambiguity or incomplete PR data.
- Always: emit exit 2 for undetermined state; `--exit-code` emits exit 1 for a
  fully determined report containing `STRANDED`.
- Never: delete branches, alter janitor deletion classification, or duplicate
  squash-detection logic.
- Never: edit `STATUS.md`, `AGENTS.md`, or workflow files in this change.

## Success criteria

- Squash-merged, contained, stranded, open-PR, and undetermined branches are
  classified without overlap.
- `gh` absence leaves git-derived `MERGED`/`CONTAINED` results usable while
  suppressing unsafe `STRANDED` claims.
- Human and JSON reports state when PR attribution is unavailable.
- Existing janitor tests, focused liveness tests, and ruff pass.

## Implementation tasks

- [x] Add failing liveness tests and confirm the expected RED state.
- [x] Add the minimal report model, tri-state wrapper, classifier, renderers,
  and CLI flags to `branch_janitor.py`.
- [x] Run GREEN tests, ancestor-only mutation proof, lint, and a live-ref report.
- [ ] Review and commit; push and open a draft PR when GitHub access is available.

## Open questions

None. The host-approved brief fixes the bucket priority and safety semantics.
