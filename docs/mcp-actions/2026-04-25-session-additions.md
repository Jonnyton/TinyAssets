# MCP Action Additions — 2026-04-25 Session

This document covers MCP actions and response field additions landed in the sprint
ending 2026-04-25. Chatbots discovering new capabilities should check here first.

---

## wiki action=file_bug

**New field in response:** `similar_found` (bool)

When filing a bug, the server checks for duplicate bugs using token-Jaccard similarity
(threshold 0.5). If a similar bug already exists, the response includes:

```json
{
  "status": "similar_found",
  "similar_bugs": [{"bug_id": "BUG-NNN", "title": "...", "similarity": 0.82}],
  "message": "A similar bug already exists. Use force_new=true to file anyway."
}
```

**New optional arg:** `force_new: bool` — bypasses dedup and mints a fresh bug ID regardless.

## wiki action=cosign_bug

New verb. Appends a +1 endorsement to an existing bug page without duplicating the report.

```json
{"action": "cosign_bug", "bug_id": "BUG-NNN", "context": "also affects v2.1"}
```

Response:
```json
{"status": "cosigned", "bug_id": "BUG-NNN", "cosign_count": 3}
```

---

## extensions action=record_remix

Records a provenance edge between two artifacts (parent → child remix relationship).

```json
{"action": "record_remix", "parent_id": "branch-abc", "child_id": "branch-xyz",
 "contribution_kind": "remix"}
```

---

## extensions action=get_provenance

Returns the full attribution lineage for an artifact.

```json
{"action": "get_provenance", "artifact_id": "branch-xyz"}
```

Response includes `edges` (list of AttributionEdge) and `credits` (list of AttributionCredit).

---

## extensions action=record_outcome

Records a real-world outcome for an artifact (publication, peer review, etc.).

```json
{"action": "record_outcome", "artifact_id": "branch-xyz", "outcome_type": "publication",
 "description": "Published in JMLR 2026"}
```

---

## extensions action=list_outcomes

Lists recorded outcomes, optionally filtered by artifact.

```json
{"action": "list_outcomes", "artifact_id": "branch-xyz"}
```

---

## extensions action=get_outcome

Retrieves a specific outcome record by ID.

```json
{"action": "get_outcome", "outcome_id": "outcome-nnn"}
```

---

## extensions describe_branch — new fields

Two new boolean fields added to the describe_branch response:

- `runnable` (bool) — false if any source_code node in the branch has no approval. Chatbot
  should surface a warning before attempting to run an unrunnable branch.
- `unapproved_sc` (list[str]) — names of source_code nodes awaiting approval, when `runnable=false`.

---

## extensions patch_branch — new fields

Two new fields in the patch_branch response for post-op verification:

- `post_patch` (dict) — re-read of the patched branch fields after write, so caller can
  confirm the update landed.
- `patched_fields` (list[str]) — names of the fields that were actually changed.
- `branch_version_id` (str) — immutable post-patch branch snapshot ID.
- `parent_version_id` (str | null) — pre-patch snapshot linked as the parent when the
  post-patch topology creates a new version.
- `content_hash` (str) / `published_at` (str) — metadata for the post-patch snapshot.

---

## extensions run_branch — new error fields

When a branch run fails, the response now includes structured failure classification:

- `failure_class` (str) — one of: `empty_response`, `graph_error`, `tool_error`, `timeout`, `unknown`
- `suggested_action` (str) — a human-readable next step (retry, fix source, contact support, etc.)

---

## universe action=inspect — new field

- `cross_surface_hint` (str | null) — guidance for non-fantasy domains. When the current
  universe has no fantasy content, this field suggests how to orient (e.g. "this looks like
  a research workflow — use extensions describe_branch to list your nodes").

---

## extensions describe_branch / get_branch — new field

- `related_wiki_pages` (list[dict]) — wiki pages semantically related to this branch,
  each with `page_id`, `title`, and `relevance_score`. Allows chatbots to surface relevant
  background knowledge automatically.

---

## Branch references: name OR ID

As of task #31, all `branch_id` parameters in `extensions` actions accept either the
canonical UUID or the human-readable branch name. The server resolves names to IDs
internally. Users can reference branches by name in chat without needing the UUID.

---

## goals action=search — multi-token aware

The `goals search` query is now multi-token: space-separated terms are ANDed together.
Previous behavior matched the entire query as a single string literal, returning zero
results for multi-word queries. Now `query: "fantasy short story"` returns goals
matching all three tokens.
