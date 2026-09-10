# Preference consumption: independent review and disposition

September10 2026, local feature worktree. Exact reviewed range
e8adb973..66bececb. Claude read-only retry completed exit0 ADAPT in454s; it read
the new integration tests but did not run them. First attempt60639 timed out at
600s with no verdict or substantive findings. Retry84693 is terminal. The wrapper
returned a stop-hook recap; full substantive response recovered from transcript
886da26b-51d9-46b2-8f19-ac779704ef69.jsonl. No approval is inferred from the timeout.

Command:

```text
python scripts/peer_agent.py claude --cwd C:/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets --timeout 900 --out output/preference-consumption-review-retry.md --prompt-file output/preference-consumption-review-retry-brief.md
```

## Required correction: accepted, implemented and locally verified

DISAGREE_CONCERN: the unpowered settings route accepts saved automatic mode,
while ordinary onboarding still produces a legacy assignment. The new runtime
refused any saved policy on that assignment, making subsequent conversation
unusable without an otherwise unnecessary manifest rebind.

Correction: saved automatic mode with no current override keeps the existing
legacy provider/default. It neither erases the saved generation nor publishes
authority. Current overrides and explicit saved choices still require an accepted
model assignment, preventing silent substitution for a user's explicit selection.
Four focused cases pass2.08s, including real native router execution and expiry
refusal. The initial new router test omitted first system, then operation; both
fixture-call errors corrected to the actual converse contract, no guard relaxed.
Combined793 Windows/795 Linux pass (3/1skips); commands in the proof file.
Correction not yet re-reviewed.

## Non-gating findings

1. ProviderUnavailableError could escape the final discovery-recheck catches.
   Fixed locally: ProviderError now becomes ProviderAuthorityHeldError at capture
   and a structured provider_authority_denied envelope at public serving enable.
   Two tests expire discovery at those real final checks; neither launches work
   or changes the binding.
2. Plan and launch refresh discovery twice: efficiency follow-up. Do not remove
   fresh authority checks; reuse must retain exact snapshot scope/freshness fences.
3. Plan engine-tools availability uses the environment predicate while the final
   config also requires granted founder context. It fails closed at the writer,
   but a shared predicate is a useful later integration cleanup.
4. Manifest set_serving returns the first planned provider, not the assignment
   anchor. Recorded explicitly in the delta spec; no anchor rewrite.
5. Native availability currently reads router._providers: brittle internal seam,
   not an authority failure. Future registry/discovery work should centralize it.

## Reviewer agreements

AGREE: discovery is outside SQL/admission; owner/home/assignment/member fences are
current; legacy-to-manifest race refuses; per-member caps cannot be relaxed by
the advisory union; current choice replaces the whole order without saving;
strict public input and explicit allowlists are preserved; default output context
accounting and corrected compute registration guidance match the implementation.

The later model_options display helper and its tests are outside66bececb and
must be reviewed with their consumer or the correction, not attributed to this
verdict. Native explicit model discovery, non-home controls, full native fallback,
unpowered catalogue ingress, clickable UI and rendered both-client proof remain
open. No push, merge, deployment or live retest claim is made.
