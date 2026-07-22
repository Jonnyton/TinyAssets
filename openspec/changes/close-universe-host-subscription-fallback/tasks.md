## 1. Contract and coordination

- [x] 1.1 Correct the P0/R2-1a coordination truth and claim the exact behavior/spec write set
- [x] 1.2 Write the proposal, security design, and `credential-vault` delta requirements
- [x] 1.3 Validate the complete OpenSpec change strictly before implementation

## 2. Red proof

- [ ] 2.1 Add and run a failing test proving a partial vault overlay retains alternate host authority
- [ ] 2.2 Add and run a failing test proving an unexpected universe credential-resolution failure returns inherited host authority
- [ ] 2.3 Add and run coverage for environment-bound universe scope without regressing host-local authority

## 3. Minimal implementation

- [ ] 3.1 Establish universe scope and strip all host subscription variables before the canonical runtime applies the universe overlay
- [ ] 3.2 Fail universe-scoped credential-resolution errors explicitly while preserving malformed-vault and host-local semantics
- [ ] 3.3 Apply the identical behavior to the packaged runtime mirror

## 4. Verification and foldback

- [ ] 4.1 Run focused credential/provider tests and mutation-check both repaired failure paths
- [ ] 4.2 Run runtime mirror parity, Ruff, full strict OpenSpec validation, and `git diff --check`
- [ ] 4.3 Obtain independent security and diff review with no critical or required findings
- [ ] 4.4 Sync the proven delta into canonical `credential-vault`, archive the change, and return STATUS R2-1a to its remaining provider-allowlist scope
