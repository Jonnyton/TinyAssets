# `docs/proofs/ui-test/` — durable final-acceptance proofs

When a browser-rendered chatbot conversation **discharges an acceptance gate**, record it here as its
own tracked file:

```
docs/proofs/ui-test/<YYYY-MM-DD>-<slug>.md
```

Example: `docs/proofs/ui-test/2026-07-14-anonymous-write-gate.md`

Then link it from the STATUS concern or PR it discharges, so the claim and its evidence point at each
other.

## Why this exists

`AGENTS.md` §"Quality Gates" makes a rendered chatbot conversation the final acceptance gate for
changes to public MCP behavior, chatbot UX, connector tool descriptions, and `tinyassets.io`. Until
2026-07-22 it named `output/user_sim_session.md` as the place to log that proof — a path that is
gitignored and **has never been added to git on any ref**. The gate ran; the evidence stayed on one
machine. 45 tracked files cited that path as their evidence base, and not one of those citations
could be followed by another provider, a reviewer, or a fresh clone.

Full finding: [`docs/audits/2026-07-22-ui-test-proof-log-is-gitignored.md`](../../audits/2026-07-22-ui-test-proof-log-is-gitignored.md).

## What belongs here

One file per **accepted proof** — not per session, not per mission, not per prompt. A curated record
written deliberately at the moment a gate is discharged. It must carry:

| Field | Why |
|---|---|
| **Date** (UTC) | `AGENTS.md` §"Truth And Freshness" requires a freshness stamp. |
| **Environment** | Which chatbot (Claude.ai / ChatGPT Developer Mode), which connector, endpoint `https://tinyassets.io/mcp`. |
| **Build sha under test** | The sha production was actually serving — `get_status` → `release_state.git_sha`. Per Hard Rule 14, merged is not deployed; a proof that does not name the build proves nothing about the build. |
| **Prompts typed** | The real user-like prompts, verbatim. |
| **Rendered result** | What the UI actually showed. Summarize; the full text stays in the local trace. |
| **Verdict** | Pass / fail, and what specifically was accepted. |
| **Trace / screenshot path** | Where the raw capture lives, even if that location is local. |

Template: [`_TEMPLATE.md`](_TEMPLATE.md).

## What does NOT belong here

- **Raw transcripts.** The rolling working log stays at `output/user_sim_session.md`, which remains
  gitignored and host-local. This directory holds the curated extract, not the capture.
- **Account identifiers.** A ui-test drives a real browser against a live authenticated service, so
  its raw capture routinely contains account emails read off OAuth consent screens — the existing
  local log contains exactly that. Record the account's **role** ("a fresh non-founder Google
  account"), never the address. This repo is public-draft by default (`AGENTS.md` Hard Rule 12).
- **Any credential material.** Tokens, bearer values, client secrets, cookies, session ids. If a
  capture contains one, it does not get redacted into a proof file — it gets treated as an incident.
- **Live production identifiers you do not need.** Universe ULIDs and run ids are fine when they are
  the evidence; drop them when they are incidental.

**Redact at write time, not at review time.** Once a value is committed it is in the history whether
or not a later commit removes it.

## What this is not

Not a substitute for the raw capture — the tester still keeps the local trace for their own session.
Not a place to back-fill proof for a gate that was discharged before this directory existed; a
verdict with no retrievable evidence should be **re-verified**, not reconstructed from memory.
