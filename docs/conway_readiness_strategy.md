# Conway Readiness Strategy

Deep research findings and day-1 discoverability plan for the TinyAssets MCP server.

**Date:** 2026-04-08
**Goal:** When Conway launches, our project is already listed, packaged, and discoverable — zero manual intervention required.

---

## Part 1: What Conway Actually Is (Verified Facts vs. Speculation)

### The Source: Claude Code Leak (March 31, 2026)

Anthropic accidentally published ~512,000 lines of TypeScript source code for Claude Code via npm (version 2.1.88). A missing `.npmignore` entry for `*.map` files shipped a 59.8 MB source map containing ~1,900 source files. This leak revealed:

- **44 hidden feature flags**, ~20 gating unreleased capabilities
- **KAIROS**: An always-on daemon mode (referenced 150+ times in source), enabling persistent background operation, `autoDream` memory consolidation, GitHub webhook subscriptions, 5-minute refresh cycles, push notifications, and file transmission
- **Conway**: A separate always-on agent environment with its own UI, extensions, webhooks, and browser control
- **Coordinator mode**: Multi-agent orchestration with shared team memory and structured approval workflows

### What Conway Is (High Confidence — from leaked code + TestingCatalog primary reporting)

Conway is a **standalone persistent agent environment** — separate from the normal Claude chat interface. It operates as a sidebar within Claude's interface with three core areas:

| Area | Purpose |
|------|---------|
| **Search** | Natural language queries across activities and memory |
| **Chat** | Ad-hoc agent interaction |
| **System** | Extension management, webhook config, connected clients |

Core capabilities:
- **Always-on operation** — stays active beyond foreground sessions
- **Webhook triggers** — external services can wake Conway via public URLs with cryptographic signature verification
- **Browser control** — direct Chrome integration for multi-step web tasks
- **Claude Code execution** — runs code in background
- **Connectors** — connected clients exposing tools
- **Extensions** — custom tools, UI tabs, and context handlers via `.cnw.zip` format
- **Notifications** — push notifications to users

### The CNW.zip Extension Format (Medium-High Confidence)

The leaked code references a `.cnw.zip` extension package format. What we know:

- Extensions package **custom tools, UI tabs, and context handlers**
- Users install by dropping `.cnw.zip` files into the Conway interface
- The Extensions area lives under "Manage your Conway instance" settings
- Conway acts as an **"app store for agent capabilities"** — a curated marketplace/directory

### What We DON'T Know Yet (Speculation Zone)

- **Exact `.cnw.zip` internal structure** — No manifest spec has leaked. We don't know if it's a renamed `.mcpb`, a superset of it, or something entirely new.
- **Submission process** — No developer portal, review process, or registry endpoint has been confirmed for Conway specifically.
- **Relationship to existing plugin system** — Whether Conway extensions are a new format or converge with the existing Claude Code plugin / MCPB desktop extension ecosystem.
- **Launch date** — Anthropic hasn't announced anything publicly. Could be weeks or months.
- **Whether MCP servers automatically surface** — We don't know if existing MCP tools are auto-discoverable in Conway or require repackaging.

### Credibility Assessment of the YouTube Video / Google AI Summary

The Google AI summary you received contains a mix of real information and confident-sounding extrapolation. Specifically:

- ✅ **Real:** Conway exists, uses `.cnw.zip`, has an extension/marketplace model, supports UI panels
- ⚠️ **Overstated:** The claim that you *must* adopt `.cnw.zip` to be "featured" — we don't know the submission process yet
- ⚠️ **Overstated:** The "Google Play Services lock-in" framing — this is one analyst's interpretation, not confirmed strategy
- ❌ **Missing context:** The summary ignores that Anthropic already has *three* existing extension/plugin systems (MCP servers, MCPB desktop extensions, Claude Code plugins) that Conway will almost certainly build on rather than replace

---

## Part 2: The Existing Anthropic Extension Ecosystem (What's Real Today)

Conway won't exist in a vacuum. Anthropic already has three overlapping extension surfaces, and Conway will almost certainly layer on top of them:

### Layer 1: MCP Servers (Standard Protocol)

- Open standard (Model Context Protocol)
- Your TinyAssets MCP server already implements this via FastMCP
- Any MCP-compatible client can connect
- **This is your universal foundation — keep it.**

### Layer 2: MCPB Desktop Extensions (.mcpb files)

- Zip archives containing an MCP server + `manifest.json`
- One-click installation in Claude Desktop
- Runs locally via stdio transport
- **Submission:** Form at `forms.gle/tyiAZvch1kDADKoP9`
- **Requirements:** Tool annotations on all tools, privacy policy, 3+ working examples, manifest v0.3+
- **Discovery:** Searchable in Claude Desktop directory; Teams/Enterprise admin allowlisting
- **This is the closest existing analog to what Conway extensions will likely be.**

### Layer 3: Claude Code / Cowork Plugins

- Git-based marketplace system (`marketplace.json`)
- Bundle MCP servers, skills, agents, hooks
- Official marketplace: `anthropics/claude-plugins-official` (auto-available)
- Community marketplace: `anthropics/claude-plugins-community`
- **Submission:** `claude.ai/settings/plugins/submit` or `platform.claude.com/plugins/submit`
- **Verification:** Automated security scanning + optional "Anthropic Verified" badge
- **Top plugins:** 100K-450K+ installs
- **This is the distribution channel with the most reach today.**

### The Likely Truth About CNW.zip

Based on the pattern of how Anthropic builds, `.cnw.zip` is almost certainly an evolution of `.mcpb` — not a replacement of MCP. The strongest evidence:

1. MCPB files are already zip archives with a manifest.json + MCP server
2. Conway's extension capabilities (tools, UI tabs, context handlers) map directly to what MCPB already provides plus UI components
3. Anthropic has consistently built on MCP as the foundation layer
4. The leaked manifest example (from the blog analysis) shows the same tool/capability/auth structure as MCP

**Our bet:** If we're in the MCPB directory AND the Claude plugin marketplace AND running a clean MCP server, we will be automatically or trivially discoverable in Conway on launch day. The `.cnw.zip` format is likely either identical to `.mcpb` with additional UI metadata, or Conway will natively surface existing MCPB/plugin entries.

---

## Part 3: Day-1 Readiness Plan

### Strategy: Cover All Three Surfaces Now

We don't wait to find out which surface Conway inherits from. We ship on all three *today*, so whichever one Conway picks up, we're already there.

### Track A: MCP Server (Universal Foundation) ✅ ALREADY DONE

Your TinyAssets MCP server (`universe_server.py`) is already a compliant MCP server via FastMCP with Streamable HTTP transport. It exposes:
- `universe()` tool — comprehensive universe operations (read/write/control)
- `extensions()` tool — custom node registration system
- MCP prompts (`control_station`, `extension_guide`)

**Remaining work:**
- [ ] Ensure all tools have MCP tool annotations (`readOnlyHint` / `destructiveHint`) — **this is a hard requirement for directory listing**
- [ ] Add comprehensive tool descriptions that Conway's AI can parse for discoverability
- [ ] Register on the official MCP registry at `registry.modelcontextprotocol.io` (you noted this in STATUS.md already)

### Track B: MCPB Desktop Extension (.mcpb package)

Package the TinyAssets MCP server as a one-click installable desktop extension.

**What to build:**
1. **`manifest.json`** following MCPB v0.3+ spec:
   ```json
   {
     "name": "tinyassets-universe-server",
     "version": "0.1.0",
     "display_name": "TinyAssets Server",
     "description": "Goal-agnostic daemon engine. Summon the daemon, bind it to a domain, and let it drive. Connect to living universes, submit direction, register custom workflow nodes, and steer autonomous output — all through natural conversation.",
     "icon": "icon.png",
     "tools": [...all tool definitions with annotations...],
     "user_config": {
       "universe_path": {
         "type": "string",
         "description": "Path to universe output directory",
         "default": "output/default-universe"
       }
     },
     "privacy_policies": ["https://your-domain.com/privacy"]
   }
   ```
2. **Bundled server** — Node.js wrapper or Python executable
3. **Icon** — 512x512 PNG with transparency
4. **3+ working examples** in documentation
5. **Privacy policy** in README and manifest

**Submit to:** Anthropic's MCPB directory form

### Track C: Claude Code / Cowork Plugin

Package as a plugin for the Claude Code / Cowork marketplace.

**What to build:**
1. **Plugin repository** with `.claude-plugin/marketplace.json`:
   ```json
   {
     "plugins": [{
       "name": "fantasy-author",
       "description": "Autonomous fantasy novel writing — connect to living universes with AI Authors",
       "version": "0.1.0",
       "homepage": "https://github.com/your-repo",
       "skills": ["./skills/"],
       "mcpServers": {
         "fantasy-author": {
           "command": "python",
           "args": ["-m", "fantasy_author.mcp_server"],
           "env": {
             "FANTASY_AUTHOR_UNIVERSE": "output/default-universe"
           }
         }
       }
     }]
   }
   ```
2. **Skills** — Port your existing `/steer`, `/status`, `/premise`, `/progress` as plugin skills
3. **Hooks** — Auto-setup hooks for first-time configuration

**Submit to:** `claude.ai/settings/plugins/submit` AND `platform.claude.com/plugins/submit`

### Track D: Conway-Specific Preparation (Hedge Bet)

Even without a confirmed `.cnw.zip` spec, we can prepare:

1. **Webhook endpoint** — Your TinyAssets MCP server already has an API. Add a lightweight webhook receiver that Conway can call to wake/trigger the daemon:
   ```python
   @app.post("/webhook/conway")
   async def conway_trigger(request: Request):
       # Verify signature (when spec is known)
       payload = await request.json()
       # Route to daemon control, note submission, etc.
   ```

2. **UI panel metadata** — Prepare a panel descriptor that Conway could render:
   ```json
   {
     "panels": [{
       "id": "universe-dashboard",
       "title": "Universe Dashboard",
       "description": "Live view of daemon status, recent activity, and story progress",
       "type": "status"
     }, {
       "id": "creative-direction",
       "title": "Creative Direction",
       "description": "Submit notes and direction to the active Author",
       "type": "input"
     }]
   }
   ```

3. **Rich tool descriptions** — Conway will use AI to decide which extensions to surface. Make tool descriptions self-explanatory and keyword-rich so Conway's search/recommendation system finds us.

### Track E: MCP Registry Listing

Register on `registry.modelcontextprotocol.io` — the official MCP registry.

**Why this matters for Conway:** If Conway surfaces MCP servers from the registry (very likely given it's Anthropic's own protocol), being listed there is automatic discoverability.

**Submit via:** GitHub PR to the registry repository.

---

## Part 4: Priority Order

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Add tool annotations to all MCP tools | Low | Required for ANY directory listing |
| 2 | Submit to Claude Code/Cowork plugin marketplace | Medium | Immediate visibility to 100K+ users |
| 3 | Package as MCPB desktop extension + submit | Medium | Claude Desktop directory listing |
| 4 | Register on MCP registry | Low | Universal discoverability |
| 5 | Add webhook endpoint to TinyAssets MCP server | Low | Conway-ready trigger surface |
| 6 | Prepare UI panel metadata | Low | Ready to package as `.cnw.zip` the moment the spec drops |
| 7 | Monitor Anthropic developer channels daily | Ongoing | First-mover on `.cnw.zip` spec |

---

## Part 5: What Makes Us Uniquely Ready

Your project is actually in an *extremely* strong position for Conway because:

1. **You already have an MCP server** — most projects don't. Conway is built on MCP.
2. **You have a remote MCP server with Streamable HTTP** — Conway uses this transport.
3. **You have a persistent daemon** — Conway is about always-on agents. Your daemon IS an always-on agent.
4. **You have a node registration system** — Conway has an extensions model. Your `extensions()` tool already lets users register custom workflow nodes.
5. **You have webhook-compatible API endpoints** — Conway uses webhooks to wake agents.
6. **You have multi-user session infrastructure** — Conway is about persistent multi-user environments.

The gap isn't capability — it's packaging and directory listing. The code is ready. We just need to wrap it in the right formats and submit it to the right directories.

---

## Part 6: The Lock-In Question

The video warns about "Google Play Services lock-in." Here's the nuanced take:

**Yes, optimize for Conway.** It's Anthropic's platform and they'll favor native extensions. But your architecture already avoids lock-in because:

- The TinyAssets MCP server speaks standard MCP — works with any MCP client
- The FastAPI layer works with any HTTP client
- The daemon is provider-agnostic (Claude, Codex, Ollama, Gemini, etc.)

**The strategy is:** Be a first-class Conway citizen AND a standard MCP server. These are not in conflict. Conway *is built on* MCP. Being excellent at MCP is being excellent at Conway.

If `.cnw.zip` turns out to require proprietary Conway-only features (UI panels, context handlers), we add those as an *additional layer* on top of our MCP server — not as a replacement for it. The MCP server remains the portable core. The Conway packaging is the distribution wrapper.

---

## Part 7: Monitoring Plan

To be truly ready on day 1, set up monitoring for:

- [ ] Anthropic developer blog (`anthropic.com/engineering`) — spec announcements
- [ ] `registry.modelcontextprotocol.io` — registry changes
- [ ] Anthropic npm packages — watch for new `@anthropic-ai/conway*` packages
- [ ] Claude Desktop release notes — Conway feature flag activation
- [ ] `github.com/anthropics` — new repos related to Conway or CNW
- [ ] TestingCatalog (testingcatalog.com) — they broke the original Conway story

---

## Sources

- [TestingCatalog: Exclusive Anthropic tests its own always-on Conway agent](https://www.testingcatalog.com/exclusive-anthropic-tests-its-own-always-on-conway-agent/)
- [Nate's Newsletter: 512,000 Lines of Leaked Code](https://natesnewsletter.substack.com/p/the-platform-play-hidden-in-512000)
- [The New Stack: Inside Claude Code's leaked source](https://thenewstack.io/claude-code-source-leak/)
- [Dataconomy: Anthropic Tests Conway](https://dataconomy.com/2026/04/03/anthropic-tests-conway-platform-for-continuous-claude/)
- [WaveSpeedAI: Claude Code Hidden Features](https://wavespeed.ai/blog/posts/claude-code-hidden-features-leaked-source-2026/)
- [TJ Robertson: What Is Claude Conway](https://tjrobertson.com/what-is-claude-conway/)
- [Atal Upadhyay: Claude Conway Decoded](https://atalupadhyay.wordpress.com/2026/04/06/claude-conway-decoded-anthropics-always-on-ai-agent-platform/)
- [HTX Insights: Anthropic Tests Lobster Conway](https://www.htx.com/news/Project%20Updates-P3JQPbyZ/)
- [Claude Code Docs: Discover Plugins](https://code.claude.com/docs/en/discover-plugins)
- [Claude Help Center: Building Desktop Extensions with MCPB](https://support.claude.com/en/articles/12922929-building-desktop-extensions-with-mcpb)
- [Claude Help Center: Local MCP Server Submission Guide](https://support.claude.com/en/articles/12922832-local-mcp-server-submission-guide)
- [Anthropic: Plugins for Claude Code and Cowork](https://claude.com/plugins)
- [TestingCatalog: Anthropic prepares managed Conway Agent for Businesses](https://www.testingcatalog.com/anthropic-likely-tests-managed-24-7-ai-agents-for-businesses/)
- [Fortune: Anthropic leaks Claude Code source](https://fortune.com/2026/03/31/anthropic-source-code-claude-code-data-leak-second-security-lapse-days-after-accidentally-revealing-mythos/)
- [AI Tools Navigator: Anthropic Conway reveals](https://toolnavs.com/en/article/1269-anthropic-conway-reveals-claude-is-making-up-for-the-last-piece-of-always-on-age)
