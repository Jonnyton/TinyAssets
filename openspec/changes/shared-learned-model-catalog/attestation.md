# Publication by attestation (founder design, 2026-09-26, supersedes the threshold)

Founder, verbatim: *"when user is adding a model it works kinda like a web fetch,
your universe model figures out if its a public release or something else and if its
unsure it can ask the user or not share it"*.

This replaces the distinct-owner threshold as the publication rule. The threshold was
refuted in review round 3: two genuinely different people can use one organisation's
private deployment selector, so "used by two owners" never implied "public". An
org-private ARN will not appear on a public release page, so the attestation does what
the threshold could not.

The platform still supplies no LLM. The judgment is the OWNER'S OWN universe agent's;
the platform only checks something deterministic and vendor-free.

## Shape

1. An owner-typed id that works stays on that owner's own list, marked **unshared**.
   Already built (`_own_verified_candidates`); unchanged by this.
2. A new owner-authorized write op attests the id is a **public release**, naming an
   evidence URL: a public page the agent found (provider docs, a release note).
3. The platform verifies deterministically: a public `https` page, and the EXACT id
   string present on it. Only then is the id published, with source kind, id,
   first-verified time and the evidence URL -- no user data.
4. Unsure -> the agent asks the owner through the normal request card, or does not
   share. **Default: not shared.**
5. One line of served guidance where the agent learns a model worked.

## DECIDED (2026-09-26): option 2, no platform egress at all

The founder settled it: *"there is no platform llm, just other users"*, and
independent verification comes from OTHER USERS' agents, each fetching with its own
sandboxed web capability. So the platform makes no outbound request, there is no new
egress primitive, and no SSRF oracle to bound. The analysis below is kept because it
records WHY, and it is the reason the staged shape exists at all.

## Built shape

1. The owner's agent attests: id + evidence URL (query and fragment stripped) + the
   exact snippet it read. The platform checks only that the id appears in the
   snippet, then the item is PENDING and shared with nobody.
2. Two or more distinct OTHER owners' agents, each on a model that is not superseded
   by a newer sibling already published, independently re-check -- each fetching the
   stripped URL itself or citing its own public source -- and submit a confirmation
   with its own snippet. The platform runs the same check on each. The attester's own
   universes never count.
3. Published at two confirmations. Unsure at any stage means ask the owner or do not
   share. Default: not shared.
4. Pending items are an opt-in queue any owner's agent may read, carrying the source
   kind, the id and the page -- and no owner data. Users build the loop; there is no
   platform worker.

**"Smart recent big model" without vendor names.** A confirming model qualifies when
nothing known is NEWER in its class (`model_class.superseded_by`). Not "is a member of
the published newest set", which deadlocks: an empty catalog has no newest set, so no
confirmer could ever qualify and the catalog could never fill. "Not superseded" is
monotone -- a first confirmer qualifies, and the bar rises on its own as the catalog
grows -- and it cannot be gamed downward, because publishing more of your own OLDER
ids never makes yours the newest of its class, and the id is the one a turn actually
ran on.

## Superseded analysis: why there is no grant-free public fetch

This is the part that cannot be built from what exists, and it is an authority change
rather than plumbing.

Every hardened outbound path in the substrate fetches **through an owner's HTTP grant
with a per-connection endpoint allowlist**. `read_granted_discovery_document`
(`providers/discovery_http.py:100`) requires a `grant_id`, an unrevoked connection, a
GET scope, and `_enforce_endpoint_allowlist`. The `public_https_get` redirect mode
(`storage/outbound_connections.py:1831`) is a redirect policy for an ALLOWLISTED
endpoint, not a grant-free fetch.

The allowlist is not incidental hardening -- it is the stated boundary. From
`storage/outbound_connections.py:1283`:

> The real confidentiality boundary is the per-connection endpoint allowlist PLUS
> fixed destination-specific response projections

The same comment block records live gaps that matter for an arbitrary destination:
org-specific NAT64 prefixes read as global-unicast, and DNS resolution sits outside the
request deadline.

An owner will not have an HTTP grant to their vendor's docs site, so step 3 as written
needs a fetch to a host **the agent chooses**. That is a new egress primitive, and an
agent-chosen destination plus a returned result is an SSRF read oracle.

## Narrowest form that keeps the founder's property

If the fetch is approved, it should be a dedicated public-page **attestation reader**,
not a general fetch, with the oracle value deliberately removed:

* `https` only; no userinfo, no credentials, no request body, GET only.
* Resolve, reject any non-global address, and pin the resolved IP for the connection
  (the existing canonical-URL parser plus the pinning connection).
* Follow **no** redirects: a redirect is a second destination the agent did not attest.
* Bounded body, bounded total deadline.
* **Return only a boolean** -- "the exact id string appears on that page". Never the
  page, never a byte of it, no status distinction beyond fetched/not-fetched. This is
  the point that collapses the read oracle to one bit per attempt.
* Rate-limited per owner, so one bit per attempt is not a usable channel either.
* The stored evidence URL is the FETCHED url with query and fragment stripped, and the
  check must pass against that stripped url. A shared table must not carry an
  agent-supplied query string: that is free-form text in a cross-user store, the same
  class of hole as the ARN and the email address in rounds 1 and 2.

## If the fetch is not approved

The owner's agent does the fetch itself (it already has a web-read capability in its
sandbox) and attests the URL **plus the exact quoted snippet** it saw. The platform
makes no outbound request at all and checks only that the id appears in the attested
snippet. Weaker -- a confused agent can attest wrongly -- but the blast radius is one
owner publishing an id their own agent vouched for under owner authorization, and it
adds no egress primitive.

Recommendation: decide this before the write op is built. The two versions differ in
authority, not just in code.
