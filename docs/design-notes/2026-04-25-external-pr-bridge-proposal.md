---
status: active
---

# External PR → patch_request Bridge

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Implements A3 from navigator v1 vision §3.
**Builds on:** navigator's canary→patch_request seam (`docs/design-notes/2026-04-25-canary-to-patch-request-spec.md`); Task #48 contribution ledger (surface 3); dev's Task #52 file_bug kind routing.
**Scope:** schema/contract design only. No code changes.

---

## 1. Recommendation — small webhook receiver, reuse existing primitives

Pick a small webhook receiver at `tinyassets/integrations/github_webhook.py` that maps GitHub PR events to existing `_wiki_file_bug(kind="patch_request")` calls. **No new MCP action; no new schema.** The PR bridge is structurally identical to navigator's canary→patch_request seam — external trigger source → server-side `_wiki_file_bug` invocation → standard wiki page lifecycle.

The deciding insight: any external system that produces patch-request-shaped artifacts (canary failures, GitHub PRs, third-party bots) should converge on the same primitive. `_wiki_file_bug` at `universe_server.py:13102` already accepts a `kind` parameter and validates it against `_VALID_BUG_KINDS`. Adding `"patch_request"` to that enum (lands with dev's Task #52) gives the bridge a stable target to call.

### Hard prerequisite — dev's Task #52

Dev is implementing `file_bug` kind-routing right now (bug / feature / design / patch_request kinds + per-kind dirs + per-prefix ID counters). This proposal **does not ship before #52**. Specifically:

- Once #52 lands, `kind="patch_request"` extends `_VALID_BUG_KINDS` (4-element set).
- Routing: `pages/patch-requests/` directory, `PR-NNN` ID prefix.
- External-PR-originated patch_requests land in `pages/patch-requests/` alongside chatbot-filed patch_requests. Same kind, different sources distinguished only by tags.

This proposal anticipates that routing pattern; the bridge invokes `_wiki_file_bug(kind="patch_request", ...)` and dev's routing layer handles the directory + ID assignment.

---

## 2. Webhook event mechanics (GitHub side)

| Aspect | Choice |
|---|---|
| **Event type** | `pull_request` (covers `opened`, `closed`, `synchronize`, `labeled`, `reopened` actions). Subset of actions handled per §3. |
| **Auth** | Webhook secret signed via HMAC-SHA256 (`X-Hub-Signature-256` header). Standard GitHub pattern. Receiver verifies signature before any payload processing — reject unsigned / bad-sig deliveries with 401. |
| **Secret storage** | `$HOME/workflow-secrets.env` per existing project convention. Env var name: `TINYASSETS_GITHUB_WEBHOOK_SECRET`. |
| **Endpoint path** | `POST /webhooks/github` mounted on the existing universe_server HTTP surface. |
| **Anti-replay** | `X-GitHub-Delivery` GUID per delivery; receiver tracks last **N=1000** GUIDs in a bounded FIFO dedup table. Replays return 200 + `{"status": "duplicate_delivery", "guid": ...}` (idempotent). Bounded eviction prevents unbounded growth. |
| **Failure mode** | If receiver is down for an outage, GitHub retries failed deliveries (its own backoff). Idempotent processing means safe replay on recovery. |
| **Payload size** | GitHub PR events are <1 MB typical; reject payloads >10 MB at the HTTP layer with 413. |

Action filter (only these are processed):

| Action | Behavior |
|---|---|
| `opened` (with `patch-request` label) | Create patch_request via `_wiki_file_bug(kind="patch_request")`. |
| `labeled` (added `patch-request` post-open) | Same as `opened` — bridge fires when label transitions add. |
| `closed` (with `merged: true`) | Update wiki page status to `merged`; emit `code_committed` contribution event (Task #48 surface 3). |
| `closed` (with `merged: false`) | Update wiki page status to `rejected_pr_closed`. No contribution event. |
| `reopened` | Revert wiki page status to `in_review`. |
| All other actions | No-op. |

---

## 3. PR-fields → patch_request mapping

Per dev #52 routing, the bridge calls `_wiki_file_bug(kind="patch_request", ...)`. The page lands in `pages/patch-requests/PR-NNN-<slug>.md`.

| GitHub PR field | patch_request arg | Notes |
|---|---|---|
| `pull_request.title` | `title` | First 100 chars; truncate with ellipsis. |
| `pull_request.body` | `observed` | Full body markdown preserved. |
| `pull_request.html_url` | `tags` (`source:github_pr,pr_url:<url>`) | URL recorded so chatbot can link back. |
| `pull_request.user.login` | `tags` (`github_handle:<login>`) | For credit threading. See §4. |
| Labels | `severity` | Inferred from `severity:P0` / `severity:P1` / `severity:P2` label; default P2 if absent. |
| `repository.full_name` | `tags` (`repo:<owner/name>`) | Per Q3 — single namespace, repo recorded in tags. |
| `pull_request.body` headings | `expected` and `repro` | Heuristic: parse `## Expected` / `## Repro` sections from body if present; else empty. |
| `force_new` | `false` (default) | Lets the existing dedup primitive cosign duplicates per BUG-NNN dedup logic at `universe_server.py:13157-13186`. |

**Wire-shape (pseudocode):**

```python
_wiki_file_bug(
    component=f"github:{repo_full_name}",
    severity=infer_severity(pr_labels),
    title=pr.title[:100],
    kind="patch_request",
    observed=pr.body or "",
    expected=parse_section(pr.body, "Expected") or "",
    repro=parse_section(pr.body, "Repro") or "",
    workaround="",
    tags=(
        f"source:github_pr,"
        f"pr_url:{pr.html_url},"
        f"github_handle:{pr.user.login},"
        f"repo:{repo_full_name}"
    ),
    force_new=False,
)
```

---

## 4. Opt-in via label + carve-outs

### Opt-in label (config-driven)

Bridge fires only for PRs carrying the configured label. **Label name is config-driven via `TINYASSETS_GITHUB_PR_LABEL`** (env var; default `patch-request`). Maintainers can rename without code changes; if the env var is unset, the default applies.

If the label is missing at PR open, no patch_request is created. Adding the label later (`labeled` action) fires the bridge retroactively.

### Carve-outs (auto-skip even with label)

Skip the patch_request creation when ANY of these match:

- **PR labels contain** `docs-only`, `format-only`, or `hotfix`. These don't need design vetting — they're mechanical.
- **PR head branch matches** `dependabot/*`, `renovate/*`, `pre-commit-ci/*` patterns. Mechanical updates from automation; no human design intent.
- **PR author is in trusted-automation allowlist** (config: `TINYASSETS_GITHUB_AUTOMATION_ALLOWLIST`, comma-separated). Default includes `github-actions[bot]`, `dependabot[bot]`, `renovate[bot]`.

Carve-out matches return 200 OK with `{"status": "skipped_carve_out", "reason": "..."}` for observability — silent skip would be confusing for maintainers debugging label-not-firing.

---

## 5. Author identification — explicit opt-in via new verb

GitHub `pull_request.user.login` does NOT auto-thread to a Workflow `actor_id`. Per Q1 recommendation (explicit opt-in matches `project_user_builds_we_enable`):

### New verb: `wiki action=link_github_handle`

Read-only initial draft (full implementation comes after PR bridge ships):

```
wiki action=link_github_handle github_handle="<login>"
  → returns { status, actor_id, github_handle, linked_at }
```

The chatbot prompts the user once: "Want credit on GitHub for your patch_requests? Share your handle." User authors the binding. Stored alongside actor identity (existing `actor` table — schema migration is dev's separate concern).

### Effect on PR bridge

Until a PR author has explicitly linked their GitHub handle, the patch_request page records `github_handle:<login>` in tags (visible in the wiki page) but does NOT create a contribution event with that actor's `actor_id`. The `code_committed` contribution event records `actor_id="anonymous"` + `actor_handle=<login>` until the user opts in.

Once linked, retroactive backfill is a separate dispatch (out of scope here). Going-forward emits use the linked actor_id.

This is consistent with CONTRIBUTORS.md (committed `87e96bb`) shape — Co-Authored-By lines reference GitHub handles even before an actor identity link exists. The link upgrades the contribution from handle-only to actor+handle.

---

## 6. Closure: PR merge / close / reject

When `pull_request.closed` event fires:

| Outcome | Wiki page update | Contribution event (Task #48) |
|---|---|---|
| `merged: true` | frontmatter `status: merged`; add `pr_merged_commit_sha`, `pr_merged_at` fields | `code_committed` event emits, surface 3 (PR). actor_id from §5 link if available. **First merge wins** — no re-emit on subsequent updates. |
| `merged: false` | frontmatter `status: rejected_pr_closed`; add `pr_closed_at`, `pr_closed_reason` fields if available | None. Closed-without-merge is not a contribution. |
| Reopen (`reopened` action, GitHub-rare) | frontmatter `status` reverts from `rejected_pr_closed` to `in_review` | None. |
| Force-push + re-merge | First merge wins; subsequent merges are noops at the contribution-event layer | First emit only. Note in attribution-layer specs that `code_committed` is once-per-merge-cycle. |

The `pr_merged_commit_sha` field links the patch_request page to the actual landed commit, enabling the bounty calc + lineage walk in Task #48 §4 to attribute the chain correctly.

---

## 7. Open questions

1. **Identity binding mechanism — explicit opt-in via `link_github_handle`.** RECOMMENDED. Closed per lead's pre-draft note + matches `project_user_builds_we_enable`. Implementation of the verb itself is a downstream dispatch.

2. **Label rename safety — config-driven label name.** `TINYASSETS_GITHUB_PR_LABEL` env var, default `patch-request`. RECOMMENDED. Closed.

3. **Multi-repo namespace.** Today's recommendation: single wiki namespace, repo recorded in tags only. RECOMMENDED for now. Phase D federation work may revisit — federated wikis would mean federated namespaces, with cross-instance reference syntax. Note for future revisit.

4. **Webhook delivery loss / idempotency.** GUID-based dedup table, bounded N=1000 FIFO eviction. RECOMMENDED. Closed.

5. **Re-merge after force-push.** First-merge-wins semantics; no re-emit of `code_committed`. RECOMMENDED. Closed. Note in attribution-layer specs (navigator's Task #58 in flight) that `code_committed` is once-per-merge-cycle.

6. **(Truly open) PR comment-as-discussion-thread mirroring.** A PR's review comments contain rich discussion that informs the patch's evolution. Should the bridge mirror PR comments back to the wiki page as `## Discussion` section updates, or stay write-once? Recommend **write-once for v1** (simpler; comments stay on GitHub side); revisit if maintainers report context loss.

7. **(Truly open) Closed-PRs that never had the label.** A PR without the label can't generate a patch_request. If a maintainer realizes mid-review that "this should have been a patch_request" and adds the label after some discussion, the bridge fires retroactively (per `labeled` action handler). But what if the label is added AFTER `closed`? Should retroactive-on-closed PRs create a patch_request anyway, or skip? Recommend **skip after closed** (the patch's lifecycle is complete; mining post-hoc is noise) but explicitly document this.

---

## 8. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No `link_github_handle` implementation.** Only the verb signature is sketched. Full implementation (storage, opt-in flow, retroactive backfill) is downstream.
- **No webhook receiver implementation.** This is a design doc; the receiver implementation lands after dev's #52 ships.
- **No multi-repo federation.** Phase D federation note.
- **No PR comment mirroring.** Q6 note for v2.
- **No retroactive contribution backfill** (linking historical PRs after a user opts in via `link_github_handle`). Separate dispatch.
- **No `_VALID_BUG_KINDS` extension.** That's dev's Task #52 work; this proposal only depends on it landing.

---

## 9. References

- Navigator v1 vision A3 surface: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §3 (surface 3) + §4 (External-PR bridge MEDIUM priority).
- Navigator's canary→patch_request seam (structural twin): `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md`.
- Contribution ledger surface 3 (`code_committed` events): `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` §3.
- Sibling design pattern: my Task #47 / #48 / #53 / #54 proposals.
- Existing `_wiki_file_bug` primitive: `tinyassets/universe_server.py:13102-13186` (kind validation at line 13141; dedup at 13157-13186).
- Existing dedup test coverage (proves `_wiki_file_bug` is the right reuse target): `tests/test_wiki_file_bug_dedup.py` + my `tests/test_wiki_cosign_flow.py`.
- Project memory: `project_user_builds_we_enable.md` (explicit opt-in for identity binding).
- CONTRIBUTORS.md (committed `87e96bb`) — reference shape for Co-Authored-By trailers.
- Hard prerequisite: dev's Task #52 (`file_bug` kind routing — bug/feature/design/patch_request kinds, per-kind dirs, per-prefix ID counters).
