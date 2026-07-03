# Universe Visibility & Access Model (learned, granular, multi-actor)

**Status:** design vision (host directive 2026-07-02). Needs host approval before
it becomes PLAN.md truth. This note captures the *direction*; the immediate
fixes below build only its foundation.

## Origin

Surfaced from a live onboarding test (fantasy author "Echoes of the Cosmos"): a
founder's private worldbuilding canon leaked to the **global/shared** wiki
instead of their own universe. The narrow fix (per-universe isolation) opened a
much larger question the host reframed: *what is the visibility/access model
across many kinds of users?*

## Principles (host, 2026-07-02)

1. **Content always writes to the founder's specific universe.** Per-universe
   isolation is absolute — a universe's canon/notes/pages live in *that*
   universe, never a shared commons by default.
2. **Universes start private.** Private is the birth state, not a platform
   choice imposed for a specific vertical.
3. **Visibility is LEARNED, not a hardcoded default.** The universe learns from
   its founder whether to stay private, go fully public, or keep some things
   public and others private. It should *infer from what the founder is doing*
   and **proactively ask / suggest** (e.g. "you mentioned a subreddit — want the
   world canon public but your drafts private?").
4. **No vertical-specific default.** Not every universe is a fantasy world. The
   platform must not bake in what *fantasy writers* want. The model generalizes.
5. **Granular.** Visibility is per-thing (per page / section / category), not a
   single universe-wide switch. Some public, some private, simultaneously.
6. **Multi-actor access control.** Beyond solo founders:
   - A private company: private long-term, **many employees each needing
     controlled access with separate authority** (roles/permissions per actor),
     **plus public customer-facing surfaces**.
   - Solo founder who **grows into a team** — the model must scale without a
     rewrite.
7. **Regulatory / best-practice awareness.** Some industries carry data
   regulations and norms (e.g. HIPAA). The universe should be able to learn and
   respect industry data-handling best practices for its domain.

## User archetypes the model must serve

- Public author (Jonathan's Echoes — world public, has a subreddit).
- Mostly-private author who wants a *few* public pieces.
- Private company: long-term private, many employees (per-actor authority),
  public customer surfaces.
- Solo → team growth.
- Regulated-industry founder (HIPAA-style constraints).

## Foundation shipping now (the 3 test findings)

These are the *base* the learned/granular/multi-actor model grows on — they do
NOT build the full model:

- **A — soul graduation:** founder-identity learning reaches the governed soul,
  not just wiki drafts (relay-routed to `soul.edit` for now; in-process learning
  deferred until `converse` has safe structured tool-use — Codex refuted parsing
  learning out of the first-person reply: injection + unguarded `soul_versions`).
- **B — organic categories:** the wiki grows custom categories per founder
  (seed defaults, not a whitelist) — a universe's knowledge shape matches its
  founder (OKF organic growth).
- **C — per-universe isolation + private default:** a founder's `write_page`
  content lands in **their** universe (private), never the shared commons. Read
  default + the full learned/granular/multi-actor visibility layer is the larger
  lane above, sequenced after these.

## Deferred to the larger lane (not now)

Learned visibility inference + proactive ask/suggest; per-page/section/category
public-private flags; multi-actor RBAC (per-employee authority); public
customer-facing surfaces; regulated-industry policy learning. Each needs its own
design pass + opposite-provider review before build.
