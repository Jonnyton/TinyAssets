# Tasks: fail-closed universe credentials

## 1. Specify and reproduce

- [x] 1.1 Record credential isolation, set-engine allowlist, and receipt requirements.
- [x] 1.2 Add a mutation-proof router regression that invokes a success-capable fake host provider and proves it is never called for a vaultless universe.

## 2. Fail closed and constrain assignment

- [x] 2.1 Strip ambient API-key and subscription auth from universe-scoped subprocess environments, then overlay only universe vault auth.
- [x] 2.2 Filter unresolved cloud credentials from universe-scoped normal and policy routing while preserving credentialless local and no-context host flows.
- [x] 2.3 Make `set_engine` persist a strict `allowed_providers` selection and reject BYO key/provider mismatches.

## 3. Add auditable receipts

- [ ] 3.1 Carry provider, model, credential class, and owner through the provider call bridge.
- [ ] 3.2 Return purpose-labelled reply/extraction receipts from public `converse`.
- [ ] 3.3 Bind public graph runs to their universe context, persist per-node payer metadata, return pending enqueue status, and expose durable receipts from `get_run`.

## 4. Verify and publish

- [ ] 4.1 Run focused tests, mutation proof, lint/type gates, and the relevant suite.
- [ ] 4.2 Sync delta specs into main specs and perform independent security/diff review.
- [ ] 4.3 Commit, push, and open a draft PR that states what now fails; do not merge.
