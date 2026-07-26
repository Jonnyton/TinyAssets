## 1. Safe restore implementation

- [x] 1.1 Add explicit local/remote archive selection and validated unique download ownership.
- [x] 1.2 Validate archive members and links, stage extraction under the resolved volume parent, and guard temporary cleanup paths.
- [x] 1.3 Stop all running volume consumers, lock per resolved volume, and implement rollback-safe same-parent directory swapping.

## 2. Verification and operations guidance

- [x] 2.1 Add executable backup round-trip, corruption, unsafe-member, swap-rollback, and concurrency coverage.
- [x] 2.2 Update the TinyAssets restore runbooks for local GitHub Release archives, retained rollback data, and caller-owned startup.
- [x] 2.3 Run shell syntax, focused restore tests, and strict OpenSpec validation.
