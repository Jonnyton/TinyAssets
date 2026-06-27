# Reddit As Source Channel

Reddit should remain useful, but it should not be the final canon authority.

Live source URLs:

- Subreddit: https://www.reddit.com/r/EchoesoftheCosmos/
- RSS: https://www.reddit.com/r/EchoesoftheCosmos/.rss
- JSON listing: https://www.reddit.com/r/EchoesoftheCosmos/.json?limit=25

Live TinyAssets wiring:

- Universe: `echoes-of-the-cosmos`
- Goal: `dd187997039b`
- Intake branch: `f8053c7ae22a`
- Canonical branch version: `f8053c7ae22a@aa8ee9e6`
- Reddit source snapshot imported on 2026-04-29 as proposal material, not canon.

## Role

The subreddit is a public contribution and discussion surface:

- prompts
- lore ideas
- questions
- community suggestions
- debate around canon direction
- lightweight onboarding

TinyAssets should become the live-state and promotion surface:

- ingest relevant Reddit material
- summarize proposals
- turn accepted ideas into branchable canon updates
- run review/gate checks
- promote accepted changes into public canon

## Source Policy

Reddit content starts as proposal material, not canon.

Suggested states:

- `submitted`
- `triaged`
- `draft-canon`
- `needs-review`
- `accepted-canon`
- `rejected`
- `archived`

## Contributor Attribution

When importing Reddit ideas into TinyAssets, preserve attribution where possible:

- Reddit username
- source URL
- date imported
- short summary
- canon decision

## Near-Term TinyAssets

1. A user or chatbot fetches the subreddit, RSS, or JSON listing.
2. The fetched snapshot is submitted to TinyAssets MCP as imported source material.
3. The `Echoes Reddit source intake` branch builds a source manifest and contribution packet.
4. A canon gate marks each packet as `needs-review`, `draft-canon`, `accepted-canon`, `rejected`, or `archived`.
5. Accepted material is promoted into canon or a GitHub PR only after review.

## Current Boundary

TinyAssets stores, reviews, and gates imported source snapshots. The branch does not yet fetch the web by itself; the caller's browser or chatbot web tool supplies the source snapshot. This is intentional for now because public publishing should stay gated.

The live smoke run for the intake branch reached the first LLM node but failed with an empty-provider response. That is a TinyAssets host/provider follow-up, not an Echoes source-wiring issue.
