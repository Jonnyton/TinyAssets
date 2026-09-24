# Model web tools can reach container-internal addresses

**Filed:** 2026-09-24, from the PR #3953 Tier 2 review (not a blocker there).
**Severity:** P1, a possible cross-user or host exposure (server-side request
forgery, SSRF).

The chat turn and workflow-node model calls keep web search and fetch. Nothing
stops a fetch aimed at `localhost`, the Docker bridge (`172.18.0.1`), other
containers or a cloud metadata address from inside the daemon container. The
daemon's own internal endpoints, or the droplet metadata service, could then
be reached by any user's prompt. This has not been verified live.

Acceptance: from a universe's model turn, fetches to loopback, private-range
and link-local addresses are refused (egress policy at the jail or network
layer, not a per-vendor tool flag), with a test. Delete this file when that
holds.
