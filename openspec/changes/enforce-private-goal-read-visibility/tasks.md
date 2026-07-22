# Tasks — enforce private Goal read visibility

## 1. Prove the defect

- [x] 1.1 Add an integration regression that creates a private Goal and reads it
      through anonymous canonical list, search, and get paths.
- [x] 1.2 Run the regression against unmodified `origin/main` and record the
      expected disclosure failure.

## 2. Enforce the contract

- [x] 2.1 Add viewer-aware filtering to `list_goals`, `search_goals`, and
      `get_goal`.
- [x] 2.2 Resolve and pass the viewer from signed request identity inside the
      Goal read handlers; never accept it from caller arguments or env fallback.
- [x] 2.3 Preserve public reads, owner reads, and trusted internal Goal loading.

## 3. Verify and publish for review

- [x] 3.1 Prove the regression green and mutation-red without weakening or
      disabling existing assertions.
- [x] 3.2 Run the Goal test slice, scoped ruff gate, and plugin mirror build.
- [ ] 3.3 Review the security diff, commit, push, and open a draft PR that states
      exposure, private-row count evidence, red/green evidence, and proposed
      STATUS concern text without editing `STATUS.md`.
