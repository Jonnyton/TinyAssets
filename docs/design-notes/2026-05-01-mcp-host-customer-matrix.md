# MCP Host Customer Matrix

Status: maintained distribution planning artifact; not a support-claim source.
Date: 2026-05-01
Current TinyAssets contract checked: 2026-07-24 against
`openspec/changes/reconcile-external-connector-manifests/`.
Vendor-specific claims retain their dated proof and require fresh revalidation.

This matrix keeps TinyAssets customer planning broader than Claude and OpenAI.
A TinyAssets customer is anyone operating an MCP-capable host: a hosted chatbot,
IDE agent, local model shell, enterprise agent builder, self-hosted chat UI, or
custom app that can connect to a TinyAssets MCP server.

The proof source for public claims remains
`docs/ops/mcp-host-proof-registry.md`. If a host is not verified there, website
copy should say "planned" or "compatible by spec, not verified."

The maintained remote contract is one product named exactly `TinyAssets` at
`https://tinyassets.io/mcp`. It advertises exactly `read_graph`, `write_graph`,
`run_graph`, `read_page`, `write_page`, `converse`, and `get_status`.
Fresh anonymous proof is currently limited to non-status `read_graph` targets
and `read_page`. Although `get_status` remains advertised, its current result
is not an external-safe projection and MUST NOT be used for anonymous or
public-host proof until OpenSpec tasks 3.1–3.2 land. Mutation, execution, and
conversation entry require OAuth.

## Host vs Client Language

MCP distinguishes the user-facing host from the protocol client. The host is
the app the user interacts with, such as Claude, ChatGPT, VS Code, Cursor, or a
self-hosted chat UI. The MCP client is the protocol component that connects
that host to one server. Product planning should use "host" for the user-facing
surface and "client" only for protocol behavior.

TinyAssets also distinguishes the human account from the host surface. Claude.ai,
ChatGPT, Claude Code, Codex desktop, local tray, CLI, and future MCP hosts are
connected apps for the same possible TinyAssets user. The same request, daemon,
approval, or user-owned universe may be inspectable from another host only when
that host has an explicit authority binding to the same TinyAssets account.
Public UX should avoid provider jargon and describe this as "same TinyAssets
account, different connected apps."

## Priority Tiers

| Tier | Meaning | Examples |
|---|---|---|
| P0 launch gates | Highest reach, hardest discoverability path, public promise blockers | Claude directory, ChatGPT App Directory, official MCP Registry |
| P1 coverage targets | Important for builders, contributors, no-chatbot-login users, and teams | Open WebUI, LibreChat, VS Code/Copilot, Cursor, Gemini CLI, Codex |
| P2 ecosystem/watch | Useful surfaces that need direct proof before public support claims | LM Studio, Jan, Goose, Zed, 5ire, OpenClaw, custom hosts |

## Current Matrix

| Host surface | User shape | Likely TinyAssets path | Discovery/install path | Status | Minimum proof |
|---|---|---|---|---|---|
| Official MCP Registry | Any registry-aware MCP host | `https://tinyassets.io/mcp` | Published `server.json` | metadata reconciliation required | Fresh listing must use exact name `TinyAssets`, canonical `/mcp`, exact seven tools, and truthful OAuth metadata |
| Claude Connectors Directory | Logged-in Claude users/admins | `https://tinyassets.io/mcp` | Anthropic directory review | fresh canonical submission needed | Directory install plus safe read and authenticated mutation proof |
| Claude custom connector | Logged-in Claude users | `https://tinyassets.io/mcp` | Custom connector settings | fresh proof needed | Claude.ai trace against canonical `/mcp` with exact name and visible result |
| ChatGPT App Directory | Eligible logged-in ChatGPT users/admins | `https://tinyassets.io/mcp` plus current app metadata/widget if required | OpenAI app submission | fresh canonical submission needed | App Directory install without Developer Mode plus OAuth read/mutation proof |
| ChatGPT guest | Logged-out browser user | None through ChatGPT apps/MCP | Not available | unsupported by ChatGPT path | Route to no-login local/self-hosted path |
| ChatGPT custom MCP/developer mode | Eligible logged-in user/workspace | `https://tinyassets.io/mcp` | Developer Mode/workspace approval | fresh registration/proof needed | Register exact name `TinyAssets`; prove safe read plus OAuth mutation |
| OpenAI API/Agents | Developer/API agent | Remote MCP tool at `https://tinyassets.io/mcp` | API configuration | planned | Exact-seven tool list plus read call and OAuth mutation boundary |
| Codex CLI/IDE | Local developer agent | MCP config to `https://tinyassets.io/mcp` | Codex config | historical proof only; refresh needed | Fresh tool-list and anonymous read; do not claim mutation without OAuth proof |
| Gemini CLI | Local developer agent | MCP server config | Gemini CLI settings | planned | Gemini CLI tool list + read call |
| VS Code/GitHub Copilot | Local IDE user | `.vscode/mcp.json` or user MCP config | MCP gallery/config/command palette | planned | Copilot Agent mode calls TinyAssets |
| Cursor | Local IDE user | MCP config to `https://tinyassets.io/mcp` | Cursor settings/add path | historical registration proof only; refresh needed | Fresh canonical tool-list/read call; mutation unsupported until OAuth proof |
| Cline/Roo/Continue/Windsurf | Local IDE agent user | MCP config or marketplace | Host-specific settings | planned | Tool list plus safe read call |
| Replit Agent | Cloud developer agent | Replit MCP integration | Replit MCP path | planned | Replit Agent invokes TinyAssets |
| Open WebUI | Self-hosted/no-hosted-chat-login user | Native Streamable HTTP to `https://tinyassets.io/mcp` | Admin Settings -> External Tools | anonymous-read-only; historical 0.9.2 proof needs refresh | Fresh non-status `read_graph` plus `read_page`; do not invoke public status; mutation unsupported without OAuth |
| LibreChat | Self-hosted/no-hosted-chat-login user | `streamable-http` to `https://tinyassets.io/mcp` | `librechat.yaml` or UI-created server | anonymous-read-only; historical v0.8.5 proof needs refresh | Fresh non-status `read_graph` plus `read_page`; do not invoke public status; mutation unsupported without OAuth |
| LM Studio | Local model user | Local or remote MCP in `mcp.json` | LM Studio Program tab or add button | planned | Anonymous read proof; mutation unsupported until OAuth proof |
| Jan | Local model user | MCP support/path to verify | App settings or bridge | watch | Do not claim until direct proof |
| OpenClaw/channel gateway | Channel user | Direct MCP support/path to verify | TBD | watch | Do not claim until direct proof |
| Microsoft Copilot Studio | Enterprise maker/admin | Remote MCP server or OpenAPI fallback | Tenant/admin tool setup | planned | Agent invokes TinyAssets under tenant policy |
| Custom customer host | Enterprise/custom builder | Host's supported MCP transport | Integration guide | compatible by spec | Contract test plus real user flow |

## Product Rules

1. Claude/OpenAI are acceptance gates, not the definition of the customer.
2. Host-native directory acceptance is stronger than custom URL support, but
   every remote registration uses the same canonical `/mcp` product.
3. Browser-only users need a hosted-chatbot path or a no-login local/self-hosted
   fallback; do not imply ChatGPT guest users can install apps/MCP.
4. Local and self-hosted users get a first-class no-chatbot-login path.
5. A support claim is scoped to the host and date in the proof registry.
6. Long-tail hosts get spec-compatible setup notes only after a tool-list/read
   proof, not from rumor or marketplace presence.
7. Cross-host continuity is account-bound, not thread-bound. A request started
   in Claude can continue in ChatGPT only when both surfaces are linked to the
   same TinyAssets account and have sufficient authority.
8. Daemon identity is stable across hosts. Summoning from a new connected app
   resolves existing user-owned daemons before creating another daemon.
9. Security-sensitive actions may require per-host re-authentication, stronger
   proof, or handoff even when the host is already linked.
10. A no-OAuth host is anonymous-read-only. Never describe it as mutation
    capable or auth-equivalent to a supported OAuth host.

## Website Implications

The `/connect` page should present a chooser by customer situation:

- "Find TinyAssets in your app/connector directory" for accepted hosts.
- "Use custom connector URL today" for hosts that support remote MCP by URL.
- "Use a no-login local/self-hosted host" for Open WebUI, LibreChat, LM Studio,
  Jan, OpenClaw, or a custom host after proof.
- "Use an IDE/developer host" for VS Code, Cursor, Codex, Gemini CLI, and
  similar tools after config proof.

Each path should show whether it is live, pending submission, planned, or
verified in `docs/ops/mcp-host-proof-registry.md`.

Account-linking copy should use product language: "same TinyAssets account,
different connected apps." Do not imply that being logged into ChatGPT, Claude,
or another provider alone grants TinyAssets account authority.

## Sources Checked

- MCP host/client distinction: <https://modelcontextprotocol.io/docs/learn/client-concepts>
- Open WebUI MCP: <https://docs.openwebui.com/features/mcp/>
- LibreChat MCP: <https://www.librechat.ai/docs/features/mcp>
- LM Studio MCP: <https://lmstudio.ai/docs/app/mcp>
- VS Code/GitHub Copilot MCP: <https://code.visualstudio.com/docs/copilot/customization/mcp-servers>
- Current TinyAssets connector contract:
  `openspec/changes/reconcile-external-connector-manifests/`
