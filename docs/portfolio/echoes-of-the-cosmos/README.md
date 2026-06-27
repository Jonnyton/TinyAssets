# Echoes Of The Cosmos

Echoes of the Cosmos is an open science-fantasy universe intended for public contribution.

It should stand as its own public universe project. TinyAssets is the current best contribution and live-state engine for it, but Echoes is not merely a subproject of TinyAssets. The universe should remain independently understandable and contributor-facing.

## Current Status

Echoes is now wired as a public TinyAssets universe and source-intake example.

Live pieces:

- canon reference guide
- Resonance magic-system reference
- live TinyAssets universe: `echoes-of-the-cosmos`
- Reddit source channel: https://www.reddit.com/r/EchoesoftheCosmos/
- Reddit RSS source channel: https://www.reddit.com/r/EchoesoftheCosmos/.rss
- TinyAssets public-source goal: `dd187997039b`
- TinyAssets intake branch: `f8053c7ae22a`
- canonical branch version: `f8053c7ae22a@aa8ee9e6`
- prior use as source material for Fantasy Writer / Fantasy Author testing

Still in progress:

- generated/promoted canon output from the first Reddit intake run
- public contributor guide
- long-running daemon/provider execution for recurring imports

## Relationship To TinyAssets

TinyAssets is the live-state layer:

- source ingestion
- branchable canon updates
- contribution review
- gates for promotion into canon
- public/community feedback loop
- future contributor rewards where appropriate

Echoes remains the public universe. TinyAssets is the engine that can host and maintain it.

## Relationship To Hex

Some of the older world/system thinking began with a physical hex-board game idea: cardboard hexagon terrain tiles and a Civilization-like strategic board-game layout. Later digital Hex and HexConquest prototypes continued that system-design thread.

This should be mentioned as origin context, but not made the main public pitch until photos/artifacts are added.

## Public Canon

The intent is for all core canon to be public.

Current staged canon:

- [CANON_INDEX.md](canon/CANON_INDEX.md)
- [ECHOES_OF_THE_COSMOS.md](canon/ECHOES_OF_THE_COSMOS.md)
- [THE_RESONANCE_Magic_System.md](canon/THE_RESONANCE_Magic_System.md)

## Contribution Surfaces

Primary surface:

- TinyAssets-hosted live universe

Secondary/import sources:

- Reddit posts and comments
- GitHub issues/discussions if enabled later
- direct pull requests to public canon docs if the repo uses PR review

Reddit should be treated as an import/source channel into the canon workflow, not the final source of truth.

The current MCP pattern is:

1. A user or chatbot fetches a public source, such as the subreddit RSS feed.
2. TinyAssets stores that snapshot in the `echoes-of-the-cosmos` universe as imported source material.
3. The source-intake branch produces a manifest, contribution packet, and canon-gate decision.
4. Reviewed material can become canon or a GitHub PR.

The branch is live and runnable, but generated output depends on a connected TinyAssets LLM host. The first smoke run reached the first LLM node and exposed a provider empty-response issue, so the wiring is live while daemon execution remains a runtime follow-up.

## Honest Public Framing

Use:

> Echoes of the Cosmos is an open science-fantasy universe wired into TinyAssets as a public canon/source-intake system. Reddit is the first public source channel; imported material is reviewed through TinyAssets gates before it becomes canon.

Avoid:

> Echoes already has a mature active community.

## Next Step

Run a configured daemon/provider against the live intake branch, review the generated contribution packets, and promote accepted additions into public canon through gates.
