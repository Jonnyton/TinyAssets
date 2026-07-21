# Tasks — universe visibility

## 1. Define the model

- [ ] 1.1 Enumerate visibility levels and the capabilities each grants to an unauthenticated reader
      (existence / metadata / content as separate grants)
- [ ] 1.2 Decide per-universe vs per-page granularity and how they compose
- [ ] 1.3 Decide the default for new universes
- [ ] 1.4 Decide disposition of the legacy universes (concordance, workflow-voice,
      echoes-of-the-cosmos, default-universe) — explicit level or recorded grandfather reason

## 2. Enforce it

- [ ] 2.1 Gate universe enumeration on the declared level
- [ ] 2.2 Gate wiki/commons reads on the declared level
- [ ] 2.3 Fail closed on an undeclared level — never default to visible
- [ ] 2.4 Raw-DML forge probe per gate, proven RED without the gate

## 3. Prove it

- [ ] 3.1 Regression test: anonymous reader against each level sees exactly the declared surface
- [ ] 3.2 Re-run the first-contact ui-test and confirm what an anonymous caller can enumerate matches
      the declared intent
