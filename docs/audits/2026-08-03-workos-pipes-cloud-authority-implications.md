# WorkOS Pipes cloud-authority implications

**Date:** 2026-08-03  
**Initial provider:** Codex  
**Required review:** Claude Code; if its hard monthly limit remains active,
use the host-approved fresh-context same-provider independent-review fallback.

## Executive judgment

WorkOS AuthKit login is not a repository credential. WorkOS Pipes is a viable
user-owned destination-credential seam: it can start a per-user GitHub OAuth
connection, retain and refresh the connected account, and vend a fresh access
token to the backend. This can replace the missing exact-repository grant
without accepting a raw token through the chatbot or using the platform
GitHub capability.

This does **not** establish requester-owned Codex/Claude compute. Cloud
activation remains blocked until a separate provider-compute assignment is
bound to the same authenticated owner and universe.

## Evidence

- Per-user GitHub OAuth authorization URL and connected-account lifecycle:
  <https://workos.com/docs/reference/pipes/connected-account>
- Fresh OAuth credential vending with automatic refresh:
  <https://workos.com/docs/reference/pipes/access-token>
- Per-user provider connection state and granted scopes:
  <https://workos.com/docs/reference/pipes/provider>

## TinyAssets mapping

| WorkOS capability | TinyAssets use | Decision |
|---|---|---|
| Per-user GitHub OAuth URL | Phone-openable connection step during existing automation setup | Adapt |
| Connected-account status/scopes | Exact destination preflight | Adopt |
| Fresh token vending | Credential-blind outbound broker; token never enters graph state or chatbot output | Adapt |
| WorkOS API key | Deployment secret required for Pipes calls; absence fails closed | Defer until host installs it |
| Shared platform GitHub capability | Must not satisfy requester-owned destination authority | Avoid |

## Smallest implementation slice

1. Add an injected WorkOS Pipes client with strict response validation and no
   token logging.
2. Return a one-time GitHub connection URL when the authenticated owner has no
   connected account, and a redacted connected status when it does.
3. Reconcile one exact `pull-request-writer` ledger grant whose credential
   reference is an opaque WorkOS Pipes locator, not a bearer token.
4. Resolve that locator only inside the existing credential-blind broker child,
   revalidating owner, repository, scope, revocation, and connection state.

## Risks and gates

- Production needs `WORKOS_API_KEY` and a configured GitHub Pipes integration;
  secret installation and dashboard configuration are host actions.
- WorkOS user ID must equal the authenticated request subject. Body, universe,
  organization, or GitHub login names cannot select the owner.
- Missing `repo` scope, `needs_reauthorization`, ambiguous organization, or an
  out-of-scope repository fails closed and mints no ledger grant.
- This solves destination authority only. Provider-compute custody still needs
  its own user-owned binding and cannot fall back to deployed Claude, Codex,
  maintainer, or market credentials.
- Build requires independent research review, focused security/broker tests,
  public canary, and rendered phone setup proof.

## Worktree landing packet

- **Branch/worktree:** `codex/cloud-drain-phone-setup-20260803` /
  `C:/Users/Jonathan/Projects/wf-cloud-drain-phone-setup-20260803`
- **Base:** `origin/main` `1e941a8e` at study time
- **Implementation write-set:** `tinyassets/integrations/workos_pipes.py`,
  `tinyassets/storage/outbound_connections.py`,
  `tinyassets/api/cloud_automations.py`, `tinyassets/universe_server.py`,
  and focused tests; coordinate with the existing cloud-drain claim.
- **First slice:** injected Pipes client plus redacted status/URL projection;
  no provider launch or cutover until review and tests pass.
- **Fold-back:** implementation PR on the cloud-drain lane; retain this audit
  as the research dependency until rendered setup and real delivery are proven.
