# Claude Directory Submission Closeout - 2026-05-02

Purpose: track what is ready for Anthropic's Connectors Directory review and
what still requires live Claude/UI or host action-time approval.

## Official Docs Checked

Checked 2026-05-02:

- `https://claude.com/docs/connectors/building/submission`
- `https://claude.com/docs/connectors/building/testing`
- `https://claude.com/docs/connectors/building/review-criteria`
- `https://claude.com/docs/connectors/faq`
- `https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy`

Review implications:

- Remote MCP servers are a supported directory submission type.
- Claude custom connector testing uses the same runtime as directory
  connectors; there is no separate staging environment.
- Reviewers functionally test each tool and scan for policy compliance.
- Tool names must be 64 characters or fewer.
- Tool descriptions must be narrow and accurate.
- Every tool must include a title and the applicable read/write annotations.
- Catch-all tools with safe and unsafe methods in one parameter are rejected.
- Servers must return actionable errors and reasonably sized responses.
- Privacy policy, support/contact, public documentation, and at least three
  working use-case examples are required.
- MCP Apps with interactive UI need 3 to 5 PNG carousel screenshots. The
  current Workflow directory surface is tool-only, not an MCP App UI surface.

## Current Workflow Packet

- Public custom connector URL: `https://tinyassets.io/mcp`
- Directory/review endpoint: `https://tinyassets.io/mcp-directory`
- Auth: no auth for the public directory surface.
- Transport: Streamable HTTP.
- Support: `https://tinyassets.io/legal#contact`, `ops@tinyassets.io`,
  `security@tinyassets.io`
- Privacy: `https://tinyassets.io/legal#privacy`
- Docs: `https://tinyassets.io/connect`, `https://tinyassets.io/proof`
- Source: `https://github.com/Jonnyton/Workflow`

Use `/mcp-directory` for reviewed host listings unless Anthropic specifically
asks to validate the full custom connector surface. The directory endpoint has
11 narrow tools and no legacy catch-all `action` router tools.

Tool annotation status:

- Source tool titles exist for all 11 directory tools.
- Source annotations include `readOnlyHint`, `destructiveHint`,
  `idempotentHint`, and `openWorldHint`.
- Tests now assert tool titles and explicit annotations.
- All tool names are below 64 characters.

## Use-Case Examples

Use these as the three-plus review examples:

1. `Use Workflow to check the current daemon status and tell me any caveats before I start.`
2. `Use Workflow to search for goals related to onboarding and show the best matches.`
3. `Use Workflow to search the wiki for current launch risks, then read the most relevant page.`
4. `Use Workflow to propose a public goal named "Reduce MCP onboarding friction" with tags onboarding,hosts.`

For write examples, do not approve the write unless the current operator has
explicit action-time approval for creating public Workflow state.

## Repo-Side Closeout

Closed in this lane:

- Website legal source now discloses chatbot connector data categories and
  retention boundaries for ChatGPT, Claude, and other MCP clients.
- Website `/connect` mobile URL copy controls now fit the full
  `https://tinyassets.io/mcp-directory` endpoint in submission screenshots.
- Submission asset pack has current `/connect` and `/legal#privacy`
  desktop/mobile screenshots.
- Ambiguous historical failed ChatGPT goal screenshots were removed from the
  local submission asset folder.
- Regression tests now assert directory tool titles in addition to annotation
  hints.

Verification from `codex/onboarding-close-gaps`,
2026-05-02T14:08-07:00 to 2026-05-02T14:12-07:00:

- `python -m pytest tests/test_directory_server.py -q` passed: 7 tests.
- Public canaries passed for `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- Tool canaries passed for both endpoints; `/mcp-directory` listed the 11
  directory tools.
- Strict live `/mcp-directory` redaction probe passed.
- `npm run check` and `npm run build` passed in `WebSite/site`.

## Remaining External Actions

These are not repo-side blockers and still require action-time approval or a
live UI surface:

- Fresh rendered Claude.ai custom connector proof with the installed Workflow
  connector. The project standard for final chatbot-surface proof is the real
  Claude.ai UI, not only direct MCP probes.
- Claude directory form contact/org fields. Earlier browser work reached page
  2 and stopped before transmitting Google identity/contact data.
- Any test-account or reviewer-credential answer if the form requires one. For
  the authless public endpoint, the truthful answer is that no credentials are
  required and the endpoint exposes a populated public review dataset.
- Agreement to Software Directory Terms/Policy.
- Final directory form submission.

## Truth Boundary

Direct MCP canaries and tool probes show protocol health. They do not by
themselves prove directory acceptance or rendered Claude UX. Keep public copy
phrased as `directory pending` until Anthropic accepts the listing.
