What surprised me: the deploy workflow already had nearly all facts needed for a release receipt; the gap was mostly that none of them were written into a machine-readable runtime artifact.

Pattern worth capturing: release observability should be deploy-published and status-read-only. That keeps `get_status` safe while still making live drift checkable by chatbots and local tools.

One thing I would do differently: start by adding the deploy workflow structure test before editing YAML, because this repo already has strong workflow-contract tests and they make the intended step ordering explicit.

---

What surprised me: merging the connector slice onto the broker world exposed privacy requirements beyond storage itself; rendered bindings could still escape through events, checkpoints, provider errors, and logs.

Pattern worth capturing: private runtime values need one ingress boundary and a complete egress audit. In-memory execution, recursive redaction, author-scoped lookup, and destination-resolved credentials form one invariant rather than separate fixes.

One thing I would do differently: run the binding concurrency and persistence scans immediately after establishing the canonical binding write path, before expanding the connector surface tests.
