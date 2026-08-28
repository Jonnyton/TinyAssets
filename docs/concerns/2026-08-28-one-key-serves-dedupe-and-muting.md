# One key serves both "same ask?" and "what did they mute?" — so rewording defeats dedupe

**Filed:** 2026-08-28
**Verified:** 2026-08-28, observed live in the founder's own rail at
`tinyassets.io/mcp/app`.
**Severity:** P2 — cosmetic today, but it is the rail's front door and it
degrades with use.

## What the founder sees

Two tabs under **WAITING ON YOU**, visually identical:

```
API   GitHub endpoint so I can update request_theme.json
API   GitHub endpoint so I can update request_theme.json
```

They are not a rendering duplicate. They are two stored requests asking for the
**same grant** — read live via `read_graph target="pending_requests"`:

| | request 1 | request 2 |
|---|---|---|
| title | *identical* | *identical* |
| action endpoints | `api.github.com` `/repos/jonnyton/tinyassets/contents/tinyassets/onboarding/request_theme.json` `[GET, PUT]` | **byte-identical** |
| body | "…you deposited. **The**…" | "…you deposited. **Bec**…" |

The only difference is the prose. Answering either grants exactly the same
thing.

## Why

`request_from_user` builds ONE key and uses it for two different jobs
(`tinyassets/api/pending_requests.py:293`):

```python
dedupe = json.dumps([kind, title, body, fields, action], sort_keys=True, ...)
```

* **Dedupe** — "is this the same ask already pending?" `create_request`
  deduplicates on it while pending
  (`tinyassets/storage/pending_requests.py:140`).
* **Suppression** — "what exactly did the user mute?" `unsuppress` /
  `list_suppressions` key off the same string.

`body` is in the key deliberately, and for a good reason: Codex reproduced on
2026-08-27 that keying on only `(kind, title, action)` let muting *"Approve
this?"* about a harmless draft also silence *"Approve this?"* about deleting
production data, because the `answer` action normalizes to a bare
`{"type":"answer"}`. That fix was correct.

But an LLM rewrites its prose every time it raises an ask. So the same key that
makes muting precise makes **dedupe unreachable**: the agent re-raises, writes a
slightly different sentence, and the rail grows another tab for a grant that is
already pending.

## The structural point

These are two questions with different correct answers, sharing one key:

* **"Is this the same ask?"** is about the EFFECT — kind, action, fields. Prose
  is irrelevant: two requests granting identical endpoints are the same ask
  however they are worded.
* **"What did the user mute?"** is about the CONSEQUENCES they judged — which is
  why it must stay wide enough to separate a harmless approval from a
  destructive one.

Using one string for both means every change trades one defect for the other.
Splitting them is the fix: dedupe on `(kind, action, fields)`, suppress on the
full tuple including `body`.

## Why it was not fixed on the spot

It changes suppression semantics that a prior cross-family review ruled on, and
the muting behaviour is security-adjacent (a too-narrow *dedupe* key merely
clutters; a too-broad *suppression* key silences a real warning). It wants its
own change with its own review, not a fold-in to a transport fix.

## How to resolve this file

Delete it when raising the same grant twice with different prose produces ONE
tab, and the 2026-08-27 mute-collision case still passes — both proven by test,
and the rail observed clean on the live surface.
