# ui-test proof — <what this accepted>

**Date (UTC):** YYYY-MM-DDTHH:MMZ
**Tester:** <provider/session, e.g. claude-code / codex-cli / cowork>
**Discharges:** <STATUS concern, PR #, or OpenSpec change this is the acceptance proof for>

## Environment

| | |
|---|---|
| Chatbot surface | Claude.ai · ChatGPT Developer Mode |
| Connector | TinyAssets, installed and visible in the UI |
| Endpoint | `https://tinyassets.io/mcp` |
| **Build sha under test** | `<sha>` — from `get_status` → `release_state.git_sha` |
| Sha contains the change? | yes / no — `git merge-base --is-ancestor <change-sha> <deployed-sha>` |
| Account role | e.g. "anonymous (no auth)" · "a fresh non-founder Google account" · "founder" — **role, never the address** |

## Prompts typed

Verbatim, in order, as a real user would type them.

1. `…`
2. `…`

## Rendered result

What the UI actually showed. Summarize — the full text stays in the local trace. Quote the specific
rendered strings the verdict depends on.

## Verdict

**PASS / FAIL** — <exactly what was accepted, and what was not covered>

## Raw capture

- Trace: `output/claude_chat_trace.md` (local, not tracked)
- Session log: `output/user_sim_session.md` (local, not tracked)
- Screenshots: `<path>`

## Redaction note

State that the secrets/PII check was done and what was removed, e.g. "OAuth consent screen showed a
Google account address; recorded as role only." If nothing needed removing, say that.
