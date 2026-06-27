# Tiny Assets → TinyAssets Site Merge — Context

## What we have

### 1. Live public site: tinyassets.io
- Title: "Asset Backed Currency - Tiny Assets"
- Hero: **"Portfolio Backed Currency"** — "Tiny derives its value from a diverse portfolio of assets, view assets and learn more below"
- CTAs: BUY TINY · ADD LIQUIDITY
- Below hero: "Price Discovery Tools" section (chart imagery)
- Theme: dark navy + space/globe imagery, Tiny Assets cube logo (orange), purple buttons
- Has a Tiny Assets chat widget (bottom right)

### 2. GoDaddy editor draft (unpublished): same site, mid-rebrand
- Same theme/imagery, same logo, same purple buttons
- New hero: **"TinyAssets for AI work that can be inspected, improved, and rewarded"**
- Subhead: "Live MCP tools for branchable AI workflows, community bug reports, gates, and future utility-token rewards"
- New CTAs: CONNECT TO MCP · VIEW GITHUB
- New section: "Live TinyAssets Surface"
- Nav: Home · White Paper/Github · Blog · Contract Add · Tiny Alliance · Market Price · Portfolio
- Editor URL: https://websites.godaddy.com/en-US/editor/66e3611c-f5f8-497f-8b57-e3cde096e743/61e91cb9-0d09-4237-b050-af83588fc4eb/edit

### 3. Claude Designs project: "TinyAssets Design System"
- URL: https://claude.ai/design/p/48072c27-c3d6-488c-8c6d-be873636e652
- Structure: two HTML files
  - `ui_kits/tinyassets-web/index.html` — older dark-themed marketing mock
  - `/index.html` — newer parchment / dusty-rose / sage rebuild (the one Claude wants you to use)
- Rebuild aesthetic: cream parchment hero, "Summon the daemon" in serif (Fraunces), dusty-rose execution bands, sage-green active nodes, indigo lead nodes — visual language pulled from real user-made workflow diagrams
- Content: showcase workflows
  - Dev-team scaling (single-node lifecycle → 3 → 5 → 10 → 20 nodes, gate routing matrix, parallel zones, Gantt timeline)
  - Book publishing pipeline (Scribe critique loop, canon retrieval router)
- Interactivity: clickable nodes open right-side detail drawer, lifecycle animations, toggle annotations
- Brand chrome: kept dark ink + ember (navbar/hero), but diagrams render in parchment palette
- Nothing about Tiny Assets the token, contract address, market price, portfolio, etc. — pure TinyAssets product marketing

## The user's goal
- **Lead with TinyAssets** as the primary product (matches the GoDaddy draft direction)
- **Token (Tiny Assets) is secondary** — future reward mechanism, small section on the site, not the headline
- Build as **custom HTML/JS** to host on the GoDaddy domain (likely static hosting, not the GoDaddy site builder)
- Project lives at `C:\Users\Jonathan\Projects\TinyAssets\WebSite`

## What's still missing
- The actual HTML/CSS/JS source of the Claude design (can't scrape — JS blocked on claude.ai by browser extension)
- Inventory of the other tinyassets.io pages (Blog, Portfolio, Tiny Alliance, Contract Add, Market Price, White Paper)
- Token info to keep: contract address, the GitHub repo URL, MCP connection details, any utility documentation
- Decision on tech stack: vanilla HTML/CSS/JS vs a framework (e.g. just static, or Astro/Next/Vite for componentization)
