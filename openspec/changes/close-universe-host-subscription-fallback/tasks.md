## 1. Contract and coordination

- [x] 1.1 Correct the P0/R2-1a coordination truth and claim the exact behavior/spec write set
- [x] 1.2 Write the proposal, security design, and `credential-vault` delta requirements
- [x] 1.3 Validate the complete OpenSpec change strictly before implementation

## 2. Red proof

- [x] 2.1 Add and run a failing test proving a partial vault overlay retains alternate host authority
- [x] 2.2 Add and run a failing test proving an unexpected universe credential-resolution failure returns inherited host authority
- [x] 2.3 Add and run coverage for environment-bound universe scope without regressing host-local authority
- [x] 2.4 Add and run a failing test proving host API-key opt-in cannot leak into a universe CLI child
- [x] 2.5 Add and run a failing test proving default CLI homes cannot recover maintainer auth
- [x] 2.6 Add and run coverage proving host-local assembly does not invoke vault helpers
- [x] 2.7 Add and run a failing test proving a nonexistent universe binding cannot fall back to host-local authority

## 3. Minimal implementation

- [x] 3.1 Establish universe scope, construct an empty-base runtime allowlist, and pin CLI auth homes before the canonical runtime applies the universe overlay
- [x] 3.2 Convert malformed or unexpected universe credential-resolution failures to sanitized provider errors while preserving host-local semantics
- [x] 3.3 Apply the identical behavior to the packaged runtime mirror

## 4. Verification and foldback

- [x] 4.1 Run focused credential/provider tests and mutation-check both repaired failure paths
- [x] 4.2 Run runtime mirror parity, Ruff, full strict OpenSpec validation, and `git diff --check`
- [ ] 4.3 Obtain independent security and diff review with no critical or required findings
- [ ] 4.4 Sync the proven delta into canonical `credential-vault`, archive the change, and remove the completed CLI-isolation row while leaving the P0 plus R2-1a/R2-1b unchanged

## 5. Opus 5 default-deny adaptation

- [x] 5.1 Rebase draft PR #1592 onto current main, claim the exact Slice A0 write set, and record the Opus 5 verdict dependency
- [x] 5.2 Capture RED for ambient direct/cloud/future authority, home/profile roots, invalid CA inputs, arbitrary overlay keys, safe runtime basics, host-local countercase, and mirror parity
- [x] 5.3 Replace the stale ADDED-only delta with a MODIFIED canonical requirement and strict-validate the change
- [x] 5.4 Implement the least-code empty-base allowlist, private universe runtime roots, recognized selected-provider overlay, and sanitized fail-loud behavior
- [x] 5.5 Apply byte-identical behavior to the packaged runtime mirror
- [x] 5.6 Run focused and surrounding GREEN, Ruff, mirror parity, strict full-tree OpenSpec validation, and diff checks
- [x] 5.6a Address Opus ADAPT findings with RED/GREEN proof for runtime-only auth homes, physical path containment, exact providers, explicit locales, real malformed/outside vaults, and explicit-universe precedence
- [x] 5.6b Reject linked vault sources before public resolver/helper reads, preserve the canonical host-local six-variable stripping contract, and broaden the documented TOCTOU boundary
- [ ] 5.7 Obtain required Opus 5 security/diff re-review with no critical or required findings
- [ ] 5.8 After the canonical vault-clobber lane releases the spec, sync/archive and retire the STATUS row in the merge lane
