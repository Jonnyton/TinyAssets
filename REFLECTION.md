What surprised me: the deploy workflow already had nearly all facts needed for a release receipt; the gap was mostly that none of them were written into a machine-readable runtime artifact.

Pattern worth capturing: release observability should be deploy-published and status-read-only. That keeps `get_status` safe while still making live drift checkable by chatbots and local tools.

One thing I would do differently: start by adding the deploy workflow structure test before editing YAML, because this repo already has strong workflow-contract tests and they make the intended step ordering explicit.

---

What surprised me: the public `category` field existed but was discarded, and the already-validated branch builder existed but was unreachable from the collapsed public handle. The onboarding failure was mostly missing routing and audience boundaries, not missing core machinery.

Pattern worth capturing: a discoverability artifact is not shipped merely because it exists in the repository. It must be bundled and idempotently seeded into the live data substrate, with a test starting from an empty volume.

One thing I would do differently: test the deploy path for documentation assets immediately after writing the first schema page; that would have avoided the temporary repo-only page implementation.
