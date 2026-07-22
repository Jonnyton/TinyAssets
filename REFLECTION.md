What surprised me: the deploy workflow already had nearly all facts needed for a release receipt; the gap was mostly that none of them were written into a machine-readable runtime artifact.

Pattern worth capturing: release observability should be deploy-published and status-read-only. That keeps `get_status` safe while still making live drift checkable by chatbots and local tools.

One thing I would do differently: start by adding the deploy workflow structure test before editing YAML, because this repo already has strong workflow-contract tests and they make the intended step ordering explicit.

---

What surprised me: stripping auth environment variables was still unsafe because both CLI tools fall back to the process user's default logged-in home; isolation must pin a private home, not merely remove a variable.

Pattern worth capturing: a cross-file credential/config update needs both an exclusive writer transaction and nonblocking shared reader snapshots. Windows requires native `LockFileEx`; the CRT read-lock constants are exclusive aliases.

One thing I would do differently: start the first RED matrix with real writer-held-lock interleavings and default-home fallback probes, rather than testing only already-pending disk state and ambient variables.
