# Workflow Public Source Intake

Echoes of the Cosmos is the first wired example of a Workflow universe that connects to a public web source through a user's chatbot or browser.

The source channel is r/EchoesoftheCosmos. Workflow treats the subreddit, RSS feed, and JSON listing as imported source material. Imported material is not canon by default.

## Live Workflow Objects

- Universe: `echoes-of-the-cosmos`
- Goal: `dd187997039b`
- Branch: `f8053c7ae22a`
- Canonical branch version: `f8053c7ae22a@aa8ee9e6`
- Wiki page: `pages/workflows/echoes-public-source-intake.md`
- Runtime bugs filed: `BUG-035`, `BUG-036`

## MCP Pattern

1. Fetch a public source URL with a chatbot web tool, browser, or HTTP client.
2. Submit the source snapshot to Workflow MCP with `universe add_canon` or `wiki ingest`.
3. Run the `Echoes Reddit source intake` branch with `universe_id`, `source_url`, `fetched_at`, and `source_snapshot`.
4. Review the source manifest, contribution packet, and canon gate decision.
5. Promote reviewed material to canon or a GitHub PR.

## Why This Matters

This is the same pattern other Workflow users should be able to reuse for their own universes:

- a public source channel
- a universe-local imported-source snapshot
- attribution and provenance
- a branch that turns source material into review packets
- a gate before public canon or public code changes

## Current Limitations

The live branch reviews snapshots supplied by the caller. It does not yet run an autonomous browser-fetch node inside Workflow.

The latest smoke run reached the first LLM node and failed with an empty-provider response. The branch and source wiring are live; generated contribution packets need a configured Workflow host/daemon run.
