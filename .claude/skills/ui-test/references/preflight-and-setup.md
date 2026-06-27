# ui-test preflight & one-time setup (reference)

Route-specific preflight checklists + the host's one-time Claude Code CDP setup,
split out of `SKILL.md` (consulted at session start / host setup, not on the
per-step loop). The body keeps the operational rules (run your route's preflight
and stop on a blocker; the CDP-down stop rule); this file holds the details.

## Codex Claude.ai in-app preflight

When Codex runs `ui-test`, check these before the first prompt and log the result:

- The visible in-app browser tab is `https://claude.ai/` or an existing `claude.ai/chat/...` conversation.
- The conversation can use the TinyAssets connector at `https://tinyassets.io/mcp`.
- The host-visible tab is the same one Codex is reading and typing into.

If login, connector installation, or the in-app browser itself is unavailable, stop the mission and name that exact harness blocker. Do not report `claude_chat.py status` or CDP failure as a blocker for the Codex route.

## ChatGPT live preflight

When using the Anthropic / Cowork ChatGPT route, check these before the first prompt and log the result:

- The visible tab is `https://chatgpt.com/` or an existing `chatgpt.com/c/...` conversation.
- Developer mode is enabled for the conversation.
- The composer shows the `Workflow` connector/tool as available.

If any item is missing, stop the mission and ask the host to fix that exact item. Do not test through a fresh profile or a direct MCP call.

## Claude Code CDP setup the host does once (not you)

For the Claude Code route, the host launches Chrome with:

```
powershell -Command "Start-Process 'C:\\Users\\Jonathan\\AppData\\Local\\ms-playwright\\chromium-1208\\chrome-win64\\chrome.exe' -ArgumentList '--user-data-dir=C:\\Users\\Jonathan\\.claude-ai-profile','--remote-debugging-port=9222','--no-first-run','--disable-blink-features=AutomationControlled','https://claude.ai/new'"
```

logs into claude.ai in that window only if the test route needs authenticated Claude access and the profile's session is not already persisted (the `--user-data-dir` caches auth; a returning host is often already logged in and goes straight to the chat), confirms the TinyAssets connector is on, and keeps the window visible. Before you act, verify with:

```bash
python scripts/claude_chat.py status
```

If it returns non-zero on the Claude Code route, the CDP-backed browser is not up — **SendMessage the lead** and wait. Do not proceed on that route. This does not apply to the Codex in-app browser route.
