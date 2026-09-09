# Independent shape review

2026-09-08, Claude subscription peer, 202 seconds, exit 0:
`python scripts/peer_agent.py claude --out output/storage-observation-shape-claude.md --prompt-file output/storage-observation-shape-brief.md --timeout 480`.

Verdict ADAPT; shape AGREE. Four design-level adaptations adopted before build:
exclude cleanup-confirmed AVAILABLE scratch rows and treat derived-leaf ENOENT
as absence; enumerate reasons without exception text; validate lease IDs and
non-negative generations; normalize TTLMemo's timed-out None to contention.
The review explicitly permits building after these adaptations, with no further
shape round. Concrete bounds, scope/non-atomic caveats and workspace quarantine
classification were also added. Forged-authoritative-row size attribution is a
recorded residual, not a new authority mechanism in this slice.

Exact-head implementation/basic-safety approval, Linux proof and delivery gates
remain pending. No broader policy or owner acceptance is inferred.
