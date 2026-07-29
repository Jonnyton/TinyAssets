# Opposite-provider review

- Reviewer: Claude Haiku through the subscription CLI
- Date/environment: 2026-07-29, Windows linked worktree
- Initial verdict: `ADAPT`
- Finding: make the existing unconditional
  `-c approval_policy=never` write-mode invariant explicit in tests.
- Adaptation: `test_write_codex_command_grants_only_the_resolved_git_common_dir`
  now asserts the policy alongside `danger-full-access`, `--add-dir`, and the
  absence of `--full-auto`.
- Re-review verdict: `APPROVE`
- Re-review evidence: the policy is constructed before the mode branch;
  six peer-launcher tests pass; the hypothetical quote-in-Windows-path concern
  is outside supported Windows path syntax.
