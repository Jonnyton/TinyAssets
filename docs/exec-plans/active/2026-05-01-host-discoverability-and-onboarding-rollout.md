# Host Discoverability And Customer Onboarding Rollout

Date: 2026-05-01
Status: active seed plan
Owner: lead + codex-gpt5-desktop

## Trigger

The host reframed today's work around discoverability and easy use across all
customer surfaces, not only Claude and OpenAI. The pasted ChatGPT Apps
conversation promoted one specific implication: ChatGPT Apps are a first-class
host and widget surface for Workflow live state, but they must not become the
source of truth.

## North Star

A Workflow customer is anyone using a chatbot, local model shell, IDE agent,
enterprise agent builder, self-hosted chat UI, channel gateway, or custom app
that can connect to a TinyAssets MCP server.

The rollout must make three paths explicit and carry them all the way to
native discovery where the host supports it:

1. Logged-in chatbot users: Claude, ChatGPT, Mistral Le Chat, Perplexity, Grok,
   Copilot Studio, and similar hosted chat products.
2. No-chatbot-login users: LM Studio, Jan, Open WebUI with auth disabled,
   OpenClaw channel users, and custom/self-hosted chat UIs.
3. Developer/IDE users: Codex, Gemini CLI, VS Code/Copilot, Cursor, Cline/Roo,
   Continue, Windsurf, Replit Agent, and similar MCP-capable tools.

## Existing Assets

- `PLAN.md` already defines the user capability axis: browser-only vs
  local-app, orthogonal to MCP host provider.
- `PLAN.md` API/MCP Interface already says MCP clients are control stations;
  the daemon remains the author.
- `PLAN.md` Distribution And Discoverability already points to the host matrix.
- `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md` is the current
  service-by-service host matrix.
- `WebSite/site/src/routes/connect/+page.svelte` already names Claude and
  ChatGPT as gates rather than the boundary and shows P0/P1/P2 host coverage.
- `ideas/PIPELINE.md` contains "ChatGPT Apps as first-class host + live-state
  surface"; this plan promotes it out of the idea queue.
- `docs/design-notes/2026-04-22-mcp-tool-surface-scaling.md` covers tool
  discoverability, progressive discovery, resources, prompts, and schema
  bloat.
- `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md`
  covers the future `discover` primitive, rankings, remix, and public previews.
- `docs/specs/2026-04-19-connectors-two-way-tool-integration.md` covers
  pushing final artifacts into the user's actual tool boundary.
- `docs/conway_readiness_strategy.md` covers registry/packaging readiness for
  Anthropic extension-style surfaces.
- `scripts/mcp_public_canary.py`, `scripts/mcp_tool_canary.py`,
  `scripts/uptime_canary.py`, and `.github/workflows/uptime-canary.yml` cover
  public endpoint proof.
- `docs/ops/mcp-directory-rollout-action-queue.md` is the current execution
  queue after `/mcp-directory` shipped live.

## Design Decisions

1. ChatGPT Apps are a host/UI wrapper over the same Workflow backend, not a
   replacement architecture.
2. Workflow backend owns authoritative state: nodes, branches, artifacts,
   goals, bids, permissions, collaboration rows, and visibility decisions.
3. Host widget state is ephemeral: selected node, active tab, zoom, filters,
   expanded panels, and temporary form state.
4. Cross-session preferences only persist when explicitly written to Workflow
   storage through a grounded tool/RPC.
5. Directory/app metadata is product UX. Tool names, descriptions, annotations,
   scopes, and examples are part of the public interface.
6. "No chatbot login" is a product path, not a protocol claim. It means the
   user can use an MCP-capable local/self-hosted/channel surface without
   logging into Claude/ChatGPT/Gemini/etc.
7. Every claimed host gets an acceptance proof. Otherwise the copy must say
   "compatible by spec, not verified yet."
8. A host-directory rollout is not complete at "docs live" or "custom URL
   works." Completion means the host listing is accepted, a normal user can
   add/use Workflow without Developer Mode or custom URL friction, and at
   least one real or user-sim first-use trace exists.

## Ecosystem Default Strategy

The broad goal is not just "users can paste an MCP URL." The goal is that when
a user, chatbot, workspace admin, or agent host looks for a way to create,
browse, collaborate on, remix, or run Workflow nodes, Workflow is already the
obvious, trusted, verified option in the surface they are using.

Important reality check: hosted chatbots should not silently connect arbitrary
third-party tools without user or admin consent. The maximal win is therefore:

- TinyAssets appears in the host's native app/connector directory or MCP registry.
- The host can understand from metadata what Workflow is for.
- The host can recommend Workflow when user intent matches.
- The user or admin can connect it in one or two steps.
- The first successful tool call creates visible value immediately.
- The host and user can trust that the endpoint is stable, scoped, and safe.

### Discovery Rails

| Rail | Who discovers us | What must exist | Success signal |
|---|---|---|---|
| Official MCP Registry | MCP clients, aggregators, IDE agents, future host search | Valid `server.json`, verified namespace, remote endpoint metadata, CI publish | TinyAssets appears via registry API/search and can be installed from registry metadata |
| ChatGPT App Directory | ChatGPT users and workspace admins | Apps SDK submission, app manifest, widget, OAuth/safety docs, test cases | Workflow listed/discoverable in ChatGPT and invokable from chat |
| Claude Connectors Directory | Claude users/admins | Directory review package, metadata, icon/favicon, examples, privacy/safety docs | TinyAssets appears as a trusted Claude connector path, not only custom URL |
| Mistral Le Chat connector directory | Le Chat users/admins | MCP connector listing/submission path, verified remote URL, scoped auth docs | Workflow can be selected from preconfigured connectors or added with clear proof |
| Microsoft Copilot Studio | Enterprise builders/admins | Custom MCP connector/Power Platform package, OpenAPI fallback if needed | A maker can add Workflow to an agent without hand-translating tool semantics |
| IDE host rails | Developers and OSS contributors | `.mcp.json`, `.vscode/mcp.json`, Cursor add button, Gemini CLI config, README badges | A repo/IDE can suggest or add Workflow with one command/click |
| Local/self-hosted chat rails | No-chatbot-login users | Open WebUI, LibreChat, LM Studio, Jan, OpenClaw examples; Streamable HTTP/OpenAPI bridge where needed | User can use Workflow without logging into a hosted chatbot |
| Web/search/LLM docs rail | Chatbots and search systems reading public docs | `llms.txt`/AI-readable docs, stable landing pages, schema/meta tags, canonical examples | A model answering "what MCP should I use for X?" can correctly pick Workflow |
| Partner/maintainer rail | Host platform teams | Submission kits, compliance pack, stability proof, responsive issue/PR workflow | Host maintainers are willing to list, recommend, or fix integration bugs with us |

### What "Default Choice" Means

Workflow becomes the default choice when it wins all four layers below:

1. Category language: hosts and users know what bucket Workflow owns.
   Working label: "live collaborative tinyassets/node daemon for AI agents."
2. Metadata match: tool/app descriptions are short, action-oriented, and
   aligned with the intents hosts route on: create, browse, remix, collaborate,
   run, inspect, publish.
3. Setup trust: every public listing links to the same stable endpoint,
   privacy/safety page, scope list, and proof registry.
4. First-use activation: the first prompt after connecting can produce a visible
   node, browse result, branch run, or collaboration artifact without reading
   developer docs.

Do not position Workflow as "an MCP server." Position it as the thing a chatbot
uses when the user wants durable AI work that persists beyond the current chat.

### Full Customer Rollout Shape

| Customer | What they should experience | Primary path |
|---|---|---|
| Claude Free/Pro user | Claude can find/add Workflow as a connector; Free limitation is clear | Claude directory + custom connector fallback |
| ChatGPT Free user | If app access is available for their plan/region, Workflow is in Apps; otherwise no-login alternatives are shown | ChatGPT App Directory + local/self-hosted fallback |
| ChatGPT guest user | Clear explanation that guest chat cannot connect apps/MCP; offer no-chatbot-login path | `/connect` guest route |
| Workspace admin | Approve Workflow once for team use, with scopes, tests, safety docs, and support link | ChatGPT/Claude/Mistral/Copilot admin submission kits |
| Local/privacy user | Install/use through Open WebUI/LM Studio/Jan/OpenClaw without hosted chatbot login | Local pack + Streamable HTTP/OpenAPI bridge |
| Developer/IDE user | IDE finds Workflow from registry/config and can add it with one command/click | MCP Registry + `.mcp.json`/IDE buttons |
| Custom host builder | Copy a minimal integration contract and smoke test endpoint | Host builder kit + canary/proof registry |
| Chatbot vendor | See a stable, safe, popular, well-documented MCP server worth listing | Partner packet + public proof + support process |

### Product Surface Requirements

Every public surface should answer these questions without requiring the user to
understand MCP:

- What can I do with Workflow from this chatbot?
- Do I need to log into this chatbot?
- Do I need a paid plan, developer mode, or workspace admin?
- What data/actions am I granting?
- What works in this host today, and what is merely compatible by spec?
- What is the first prompt I should try?
- Where do I go when the host cannot connect?

### Machine-Readable Requirements

To let chatbots, IDEs, registries, and app directories route to Workflow
automatically, maintain these machine-readable artifacts:

- MCP `server.json` for the official registry.
- Host-specific manifests for ChatGPT Apps and any Claude/Mistral directory
  submission requirements.
- Stable public endpoints:
  - `https://tinyassets.io/mcp` for the full custom-connector surface.
  - `https://tinyassets.io/mcp-directory` for reviewed host directories and
    registry metadata.
- `/.well-known` metadata where supported by host requirements.
- `llms.txt` and concise AI-readable docs for "when to use Workflow."
- Host-specific config snippets for `.mcp.json`, `.vscode/mcp.json`, Cursor,
  Gemini CLI, Open WebUI, and local/self-hosted hosts.
- A proof registry mapping host -> verified date -> command/UI trace.

### Flywheel

The rollout should create a compounding loop:

1. Publish stable metadata in registries/directories.
2. Hosts and chatbots discover Workflow as a candidate tool.
3. Users connect with minimal friction.
4. First-use prompts create visible durable value.
5. Proof traces, examples, and public artifacts improve trust.
6. More hosts list Workflow because it is verified and already used.
7. More chatbot answers recommend Workflow because the public docs and registry
   data make the category fit obvious.

## Rollout Phases

### Gate 0: Public MCP Green

Do not ship discoverability copy, directory listings, or app submissions while
the relevant public MCP endpoint is red.

Acceptance:

- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp`
  exits 0.
- After the directory endpoint lands:
  `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory`
  exits 0.
- Latest `.github/workflows/uptime-canary.yml` run is green.
- If a 502 appears, update `STATUS.md` immediately and pause rollout work until
  recovery is verified.

Current evidence:

- Local canary on 2026-05-01 recovered to exit 0 after intermittent 502s; a
  later diagnostic had 5/5 local canaries green.
- GitHub Actions uptime run `25231089323` passed after the local 502.
- Direct `https://mcp.tinyassets.io/mcp` stayed Access-gated at HTTP 403 as
  expected.
- Treat Gate 0 as watch/flapping until the endpoint stays green long enough for
  public app/directory launch confidence.

### Phase 1: Customer-Facing Host Chooser

Turn `/connect` from one generic copy-paste page into a chooser:

- "I use Claude"
- "I use ChatGPT"
- "I use Mistral Le Chat"
- "I use a local model app"
- "I use Open WebUI / LibreChat"
- "I use OpenClaw / chat channels"
- "I use an IDE agent"
- "I am building a custom MCP host"

Each path should state login requirements, plan/admin requirements, setup
steps, what Workflow controls work there, and what proof exists.

Acceptance:

- A free Claude user can see that Claude requires a Claude account but supports
  a free custom connector slot.
- A ChatGPT guest user can see that guest ChatGPT cannot use Apps/MCP today,
  and gets a no-chatbot-login alternative instead of a dead end.
- A local user can copy LM Studio/Open WebUI/OpenClaw-ready config without
  reading developer docs.

### Phase 2: P0 Hosted Chatbot Directory Work

Claude and ChatGPT remain launch gates because they are the highest-reach
browser chat surfaces.

Claude:

- Finish connector metadata and directory-readiness package.
- Submit the directory endpoint `https://tinyassets.io/mcp-directory`, not the
  legacy catch-all `/mcp` surface.
- Keep custom connector path working for Free/Pro/Max/Team/Enterprise.
- Verify with live Claude.ai `ui-test` and post-fix clean-use evidence.

ChatGPT:

- Treat Apps SDK/custom MCP as the ChatGPT distribution path.
- Resolve the workspace-admin registration issue before claiming public
  ChatGPT parity.
- Submit `chatgpt-app-submission.json` through the OpenAI app submission flow.
- Build a minimal ChatGPT App/widget plan around browse, inspect, approve, and
  run controls.
- Keep backend state authoritative and widget state ephemeral.

Acceptance:

- Claude setup works from the Connectors Directory listing, not insider
  instructions or a custom URL.
- ChatGPT setup states exactly which plans/roles support read/fetch vs
  write/modify MCP actions.
- ChatGPT App Directory use works for a normal eligible logged-in user without
  Developer Mode.
- ChatGPT guest mode is explicitly marked unsupported for MCP controls.

### Phase 3: No-Chatbot-Login Path

This is the path for users who do not want to log into a hosted chatbot
provider.

Targets:

- LM Studio: local model chat + `mcp.json` snippet for the public TinyAssets MCP.
- Jan: local app + tool-enabled model setup.
- Open WebUI: Streamable HTTP MCP setup, including the no-auth fresh-install
  caveat.
- OpenClaw: channel-gateway playbook for Telegram/WhatsApp/Slack/Discord-style
  users and smoke proof for Workflow tools.
- Custom host: minimal MCP contract test and setup snippet.

Acceptance:

- Each no-chatbot-login target has one copy-paste config or a named caveat.
- At least one target is tested end-to-end before the copy says "verified."
- The page explains that local/self-hosted users may still need model/provider
  credentials, but not a Claude/ChatGPT login.

### Phase 4: Long-Tail Host Pack

Create matrix-scoped guides for P1/P2 hosts:

- Mistral Le Chat
- Perplexity
- Grok/xAI API
- Gemini CLI
- VS Code/GitHub Copilot
- Cursor
- Cline/Roo
- Continue
- Windsurf
- Replit Agent
- Copilot Studio

Acceptance:

- Each host is classified as verified, spec-compatible, blocked by admin, or
  watch-only.
- No guide claims support based only on rumor or server-only MCP support.
- Per-host caveats include login/admin/plan requirements.

### Phase 5: Compatibility Smoke Suite

Add a host smoke harness where automation is possible.

Minimum proof levels:

- Protocol proof: `initialize`, `tools/list`, and one read-only call.
- Host proof: host UI lists Workflow tools and invokes a read action.
- Action proof: host invokes a write/approval flow safely.
- User proof: real user or user-sim completes the intended onboarding path.

Acceptance:

- Public `/connect` support labels are generated from proof status, not
  handwritten optimism.
- P0 hosted chatbots get live UI proof.
- No-login/local hosts get reproducible config snippets and at least one local
  smoke target.

## First Implementation Cards

Progress snapshot, 2026-05-01:

- Card 1 ready-draft locally: `/connect` is now a customer path chooser with
  Claude, ChatGPT, no-chatbot-login, IDE, workspace-admin, and custom-host
  paths plus launch-gate truth.
- Card 5 live-updated: `docs/ops/mcp-host-proof-registry.md` records
  per-host claim status plus local and production verification evidence.
- Machine-readable discovery live-artifact: `packaging/registry/server.json`
  validates against the official schema and points at
  `https://tinyassets.io/mcp-directory`;
  `WebSite/site/static/llms.txt` tells chatbots when to recommend Workflow and
  when to caveat host support.
- Directory endpoint live slice: `tinyassets/directory_server.py` exposes 11
  narrow tools with explicit read/open/destructive annotations and no catch-all
  `action` inputs; production `/mcp-directory` initializes and tools/list
  returns the 11 directory tools.
- Submission packets branch-ready: `docs/ops/mcp-directory-submission-packet.md`
  and `chatgpt-app-submission.json`.
- Code/deploy gate complete for both endpoints, and MCP Registry publication
  landed on 2026-05-01 as `io.github.Jonnyton/tinyassets-universe-server`.
  Product rollout is still not complete until Claude/OpenAI submissions are
  accepted and first-use evidence is recorded.

### Card 1: Publish Host Chooser Copy

Files:

- `WebSite/site/src/routes/connect/+page.svelte`
- optional `docs/connect/*.md`

Acceptance:

- `/connect` has clear paths for ChatGPT guest, Claude Free, local model, Open
  WebUI, and OpenClaw users.
- It names login/admin requirements in user language.
- It links back to the canonical MCP URL only: `https://tinyassets.io/mcp`.

Dependency: Gate 0 green.

### Card 2: Claude Directory/Metadata Kit

Files:

- connector metadata docs/artifacts to be selected during implementation
- `output/claude_chat_trace.md`
- `output/user_sim_session.md`

Acceptance:

- Directory-facing name, description, scopes, examples, and safety copy are
  ready.
- Claude submission uses `https://tinyassets.io/mcp-directory`.
- The accepted listing appears in Claude's Connectors Directory.
- A normal Claude user can add Workflow from the directory without a custom URL.
- Live Claude.ai proof is refreshed after the copy lands.

Dependency: Gate 0 green.

### Card 3: ChatGPT Apps Seed Kit

Files:

- future ChatGPT app/server metadata files
- future widget prototype files
- `docs/exec-plans/active/2026-05-01-host-discoverability-and-onboarding-rollout.md`

Acceptance:

- `chatgpt-app-submission.json` covers the first directory-safe tools and test
  cases.
- Defines the first ChatGPT widget panels, CSP, screenshots, and state split
  before pressing Submit if OpenAI's dashboard requires embedded app resources.
- Explicitly records that ChatGPT guest mode cannot use TinyAssets MCP controls
  until OpenAI supports Apps for logged-out users.
- Blocks public parity on OpenAI submission acceptance, workspace-admin
  registration where required, and live ChatGPT proof.

Dependency: host/admin action for ChatGPT workspace setup.

### Card 4: No-Login Local Pack

Files:

- `docs/connect/lm-studio.md`
- `docs/connect/jan.md`
- `docs/connect/open-webui.md`
- `docs/connect/openclaw.md`

Acceptance:

- Each doc has one minimal config, one caveat block, and one verification
  command/check.
- At least one local/self-hosted path is verified before `/connect` labels it
  as verified.

Dependency: Gate 0 green.

### Card 5: Host Proof Registry

Files:

- future `docs/connect/host-proofs.md` or structured JSON under site content

Acceptance:

- Host labels are one of: verified, setup-ready, admin-gated, spec-compatible,
  watch-only, unsupported.
- Proof records include date, host, plan/account shape, command/UI evidence,
  and remaining caveat.

Dependency: Cards 1-4.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Public MCP intermittently 502s | Directory/app work sends users to a broken endpoint | Gate 0 and uptime canary remain first in rollout |
| ChatGPT plan/role rules shift | Copy goes stale quickly | Source each claim to OpenAI docs and label last-checked date |
| Long-tail hosts support MCP partially | Users bounce on unsupported actions | Use proof labels and caveats; verify before claiming |
| Widget state leaks into product truth | ChatGPT App diverges from backend state | Backend owns all durable state; widget stores only ephemeral UI state |
| Tool schema bloat hurts discoverability | Chatbot misses relevant controls | Apply MCP tool-surface scaling note: metadata diet, resources, prompts, progressive discovery |

## Sources To Recheck During Implementation

Fresh source snapshot, checked 2026-05-01:

- Anthropic Help Center says Claude custom connectors using remote MCP are
  available on Free, Pro, Max, Team, and Enterprise plans, with Free users
  limited to one custom connector:
  https://support.anthropic.com/en/articles/11175166-getting-started-with-custom-integrations-using-remote-mcp
- OpenAI Help Center says ChatGPT apps are for logged-in ChatGPT users, with
  plan and region exceptions:
  https://help.openai.com/en/articles/11487775-connector
- OpenAI Help Center / developer docs say custom MCP apps/connectors require
  eligible logged-in plans/workspaces and developer mode or workspace approval:
  https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta
  https://platform.openai.com/docs/guides/developer-mode
- OpenAI says developers can submit apps for review/publication in ChatGPT and
  users can discover apps in the app directory:
  https://openai.com/index/developers-can-now-submit-apps-to-chatgpt
- OpenAI's app submission docs require dashboard review, org verification,
  app management permissions, a public MCP server, CSP, screenshots/test
  prompts, and publish-after-approval before App Directory listing:
  https://developers.openai.com/apps-sdk/deploy/submission
- Anthropic says its Connectors Directory showcases MCP servers that work
  across Claude surfaces and has a server review form:
  https://support.anthropic.com/en/articles/11596036-anthropic-mcp-directory-faq
- Anthropic's current connector docs reject catch-all read/write tools and
  require titles/annotations, public docs, and MCP Inspector/custom-connector
  testing before submission:
  https://claude.com/docs/connectors/building/review-criteria
  https://claude.com/docs/connectors/building/submission
- The official MCP Registry is the preview centralized metadata repository and
  REST API for publicly accessible MCP servers:
  https://modelcontextprotocol.io/registry/about
- Mistral Le Chat supports adding MCP connectors from a preconfigured directory
  or by pointing at a custom MCP-compatible server:
  https://docs.mistral.ai/le-chat/knowledge-integrations/connectors/mcp-connectors
- GitHub Copilot/VS Code supports configuring MCP servers for Copilot Chat:
  https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/extend-copilot-chat-with-mcp
- Open WebUI supports native Streamable HTTP MCP servers from Admin Settings:
  https://docs.openwebui.com/features/mcp
- Microsoft Copilot Studio can connect agents to existing MCP servers:
  https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent

- `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`
- `docs/design-notes/2026-04-22-mcp-tool-surface-scaling.md`
- `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md`
- `docs/specs/2026-04-19-connectors-two-way-tool-integration.md`
- `docs/conway_readiness_strategy.md`
- OpenAI ChatGPT Apps/developer mode docs
- Anthropic Claude connector docs
- Mistral Le Chat custom connector docs
- Perplexity MCP docs
- xAI remote MCP docs
- LM Studio, Jan, Open WebUI, LibreChat, OpenClaw docs
