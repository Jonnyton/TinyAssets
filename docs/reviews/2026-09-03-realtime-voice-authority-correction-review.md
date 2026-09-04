# Realtime voice authority correction — cross-family review status

Date: 2026-09-03
Change: `openspec/changes/add-realtime-voice-conversation/`
Requested reviewer: Claude peer (read-only)

## Scope requested

The reviewer was asked to inspect the diff for the founder's corrected authority rule:
universe-bound user resources are the only source of voice capability; platform, maintainer,
ambient, and cross-user credentials are forbidden; and a resource-less universe must see Voice as
locked before microphone or provider activity.

The requested return contract was `AGREE`, `DISAGREE_EVIDENCE` with file/line citations, or
`DISAGREE_CONCERN` with one precise unresolved concern.

## Result

The repository peer dispatcher started the read-only Claude review, but Claude exited with status
1 after 17 seconds and returned no stdout or stderr. This is not an approval. It matches the
external Claude-subscription availability problem already observed during the implementation
review. No retry loop was started.

After the attempt, current `main` added the founder's rule that the substrate may not grow
provider-specific paths. The branch was consequently reshaped to use a provider-neutral
`tinyassets.voice.v1` bridge over an exact universe-owned generic HTTP connection and grant. The
earlier failed review did not inspect that architecture, so it cannot approve it. A fresh bounded
review of the provider-neutral diff was dispatched on 2026-09-03 with the same structured verdict
contract and hard no-subagent/no-full-suite constraints; Claude again exited 1, this time after 10
seconds, with no stdout or stderr. The raw failure receipt is preserved in
`docs/reviews/2026-09-03-realtime-voice-provider-neutral-claude.md`.

The correction remains gated on a fresh opposite-provider review before landing or rollout. Local
tests and self-review are supporting evidence only. No further identical retry was started.
