# MCP Host Customer Matrix

Status: distribution planning artifact; not a support-claim source.
Date: 2026-05-01
Last checked: 2026-05-01 against selected public vendor docs.

This matrix keeps Workflow customer planning broader than Claude and OpenAI.
A Workflow customer is anyone operating an MCP-capable host: a hosted chatbot,
IDE agent, local model shell, enterprise agent builder, self-hosted chat UI, or
custom app that can connect to a Workflow MCP server.

The proof source for public claims remains
`docs/ops/mcp-host-proof-registry.md`. If a host is not verified there, website
copy should say "planned" or "compatible by spec, not verified."

## Host vs Client Language

MCP distinguishes the user-facing host from the protocol client. The host is
the app the user interacts with, such as Claude, ChatGPT, VS Code, Cursor, or a
self-hosted chat UI. The MCP client is the protocol component that connects
that host to one server. Product planning should use "host" for the user-facing
surface and "client" only for protocol behavior.

Workflow also distinguishes the human account from the host surface. Claude.ai,
ChatGPT, Claude Code, Codex desktop, local tray, CLI, and future MCP hosts are
connected apps for the same possible Workflow user. The same request, daemon,
approval, or user-owned universe may be inspectable from another host only when
that host has an explicit authority binding to the same Workflow account.
Public UX should avoid provider jargon and describe this as "same Workflow
account, different connected apps."

## Priority Tiers

| Tier | Meaning | Examples |
|---|---|---|
| P0 launch gates | Highest reach, hardest discoverability path, public promise blockers | Claude directory, ChatGPT App Directory, official MCP Registry |
| P1 coverage targets | Important for builders, contributors, no-chatbot-login users, and teams | Open WebUI, LibreChat, VS Code/Copilot, Cursor, Gemini CLI, Codex |
| P2 ecosystem/watch | Useful surfaces that need direct proof before public support claims | LM Studio, Jan, Goose, Zed, 5ire, OpenClaw, custom hosts |

## Current Matrix

| Host surface | User shape | Likely Workflow path | Discovery/install path | Status | Minimum proof |
|---|---|---|---|---|---|
| Official MCP Registry | Any registry-aware MCP host | `https://tinyassets.io/mcp-directory` | Published `server.json` | published-live | 2026-05-01 API search returned `io.github.Jonnyton/workflow-universe-server` active/latest |
| Claude Connectors Directory | Logged-in Claude users/admins | `https://tinyassets.io/mcp-directory` | Anthropic directory review | packet-ready; submission-needed | Directory install plus live Claude tool call |
| Claude custom connector | Logged-in Claude users | `https://tinyassets.io/mcp` | Custom connector settings | protocol-live; UI proof refresh needed | Claude.ai trace with visible result |
| ChatGPT App Directory | Eligible logged-in ChatGPT users/admins | `https://tinyassets.io/mcp-directory` plus app metadata/widget if required | OpenAI app submission | packet-ready; submission-needed | App Directory install without Developer Mode |
| ChatGPT guest | Logged-out browser user | None through ChatGPT apps/MCP | Not available | unsupported by ChatGPT path | Route to no-login local/self-hosted path |
| ChatGPT custom MCP/developer mode | Eligible logged-in user/workspace | `https://tinyassets.io/mcp-directory` or full `/mcp` for dev testing | Developer Mode/workspace approval | blocked by BUG-034 | Approval plus read-only tool call |
| OpenAI API/Agents | Developer/API agent | Remote MCP tool | API configuration | planned | Responses/Agents smoke list + read call |
| Codex CLI/IDE | Local developer agent | MCP config | Codex config | verified: Codex CLI 0.104.0 | 2026-05-02 proofs: isolated `codex mcp add --url` wrote Streamable HTTP config; `codex exec -m gpt-5.2` listed tools and called `get_workflow_status` |
| Gemini CLI | Local developer agent | MCP server config | Gemini CLI settings | planned | Gemini CLI tool list + read call |
| VS Code/GitHub Copilot | Local IDE user | `.vscode/mcp.json` or user MCP config | MCP gallery/config/command palette | planned | Copilot Agent mode calls Workflow |
| Cursor | Local IDE user | Cursor MCP config | Cursor settings/add path | registration-path verified; tool-call pending | 2026-05-01 CLI added isolated Streamable HTTP config; Cursor tool-list/read call still required |
| Cline/Roo/Continue/Windsurf | Local IDE agent user | MCP config or marketplace | Host-specific settings | planned | Tool list plus safe read call |
| Replit Agent | Cloud developer agent | Replit MCP integration | Replit MCP path | planned | Replit Agent invokes Workflow |
| Open WebUI | Self-hosted/no-hosted-chat-login user | Native Streamable HTTP to `/mcp-directory` or `/mcp` | Admin Settings -> External Tools | verified: local Docker 0.9.2 | 2026-05-01 proof: chat invoked `workflow_get_workflow_status` |
| LibreChat | Self-hosted/no-hosted-chat-login user | `streamable-http` MCP server config | `librechat.yaml` or UI-created server | verified: local Docker v0.8.5 | 2026-05-01 proof: chat invoked `get_workflow_status_mcp_workflow` |
| LM Studio | Local model user | Local or remote MCP in `mcp.json` | LM Studio Program tab or add button | planned | Local model invokes read-only tool |
| Jan | Local model user | MCP support/path to verify | App settings or bridge | watch | Do not claim until direct proof |
| OpenClaw/channel gateway | Channel user | Direct MCP support/path to verify | TBD | watch | Do not claim until direct proof |
| Microsoft Copilot Studio | Enterprise maker/admin | Remote MCP server or OpenAPI fallback | Tenant/admin tool setup | planned | Agent invokes Workflow under tenant policy |
| Custom customer host | Enterprise/custom builder | Host's supported MCP transport | Integration guide | compatible by spec | Contract test plus real user flow |

## Product Rules

1. Claude/OpenAI are acceptance gates, not the definition of the customer.
2. Directory acceptance is stronger than custom URL support. Keep the distinction
   visible in website copy and proof records.
3. Browser-only users need a hosted-chatbot path or a no-login local/self-hosted
   fallback; do not imply ChatGPT guest users can install apps/MCP.
4. Local and self-hosted users get a first-class no-chatbot-login path.
5. A support claim is scoped to the host and date in the proof registry.
6. Long-tail hosts get spec-compatible setup notes only after a tool-list/read
   proof, not from rumor or marketplace presence.
7. Cross-host continuity is account-bound, not thread-bound. A request started
   in Claude can continue in ChatGPT only when both surfaces are linked to the
   same Workflow account and have sufficient authority.
8. Daemon identity is stable across hosts. Summoning from a new connected app
   resolves existing user-owned daemons before creating another daemon.
9. Security-sensitive actions may require per-host re-authentication, stronger
   proof, or handoff even when the host is already linked.

## Website Implications

The `/connect` page should present a chooser by customer situation:

- "Find Workflow in your app/connector directory" for accepted hosts.
- "Use custom connector URL today" for hosts that support remote MCP by URL.
- "Use a no-login local/self-hosted host" for Open WebUI, LibreChat, LM Studio,
  Jan, OpenClaw, or a custom host after proof.
- "Use an IDE/developer host" for VS Code, Cursor, Codex, Gemini CLI, and
  similar tools after config proof.

Each path should show whether it is live, pending submission, planned, or
verified in `docs/ops/mcp-host-proof-registry.md`.

Account-linking copy should use product language: "same Workflow account,
different connected apps." Do not imply that being logged into ChatGPT, Claude,
or another provider alone grants Workflow account authority.

## Sources Checked

- MCP host/client distinction: <https://modelcontextprotocol.io/docs/learn/client-concepts>
- Open WebUI MCP: <https://docs.openwebui.com/features/mcp/>
- LibreChat MCP: <https://www.librechat.ai/docs/features/mcp>
- LM Studio MCP: <https://lmstudio.ai/docs/app/mcp>
- VS Code/GitHub Copilot MCP: <https://code.visualstudio.com/docs/copilot/customization/mcp-servers>
- Existing submission packet sources: `docs/ops/mcp-directory-submission-packet.md`
