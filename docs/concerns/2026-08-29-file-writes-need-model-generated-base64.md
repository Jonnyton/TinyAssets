# A file write through the GitHub contents API needs model-generated base64, so it corrupts the file

**Filed:** 2026-08-29, from the live naive-user retest of "finish the README PR".
**Verified:** yes — on the wire, twice in one turn.
**Severity:** P1 for the goal (a naive user's agent scoping, building and
pushing real PRs): the flow now reaches a commit, and the commit is garbage.

## What happened (production, 2026-08-29 22:05–22:20Z, universe `u-01kxm1vszd8hwp7em418asq8h9`)

The founder's message was one natural line — *"good. ok, back to the README PR
— that request was approved a while ago, so go ahead and finish it."* — no
coaching. tiny cut `auto/tiny-docs-touch-20260829d` from `main`, read
`README.md` (6,723 bytes, returned by GitHub as base64), and tried to `PUT`
it back with one line appended:

1. First attempt: `422 content is not valid Base64`.
2. Second attempt (run `0e1a960c60cc44a9`, branch shape "GitHub README Append
   Line v2", `f5fb69c17a1f`, "stricter base64 normalization"): the commit
   landed — `7de31f12`, `README.md +2/-87`. The file is 6,877 bytes in which
   **every newline is the two characters `\n`**: the model decoded the base64
   into a JSON-escaped string, appended the line, and re-encoded the escaped
   text. 87 lines collapsed onto one. GitHub accepted it because it *is*
   valid base64.

The run store shows the mechanism: the graph's first node, `build_put_packet`,
is an LLM writer whose input is the whole file as base64 and whose output must
be a JSON packet carrying the re-encoded file (`/data/.runs.db`, `run_events`
for that run). No model produces 9 KB of base64 reliably — the two failure
shapes above are the two ways it goes wrong.

tiny's own diagnosis, in the same turn: *"the right fix is to redesign this
delivery path away from model-generated base64 instead of retrying blindly."*

## The platform gap

`authenticated_external_call` (`tinyassets/effectors/authenticated_external_call.py`)
is deliberately channel-blind and passes `request.body` through verbatim
(`{...} | "..."`, dict/list JSON-encoded by the worker). There is no way for a
graph to say "encode this field for me". Any API that takes file content as
base64 — GitHub contents, GitLab files, Gists, most object stores' JSON
uploads — therefore forces the model to hand-produce base64, and every file
write a user's agent attempts through it is corruptible in this way.

## The fix (additive, channel-blind)

A body **transform** the worker applies before sending, declared in the packet
rather than performed by the model: a field whose value is
`{"$base64": "<utf-8 text>"}` is replaced by the base64 of that text (and
`{"$base64_of": "<other field>"}` / `{"$utf8_of_base64": "..."}` if reading
needs the inverse). The platform still knows nothing about GitHub — it knows
one encoding. The model writes plain text; the worker encodes; the packet
stays fully user-specified. Spec home: the outbound-channel capability's
"packet shape" requirement (see the OpenSpec change
`openspec/changes/external-call-body-encoding/`). Append-a-line then becomes:
read (decode server-side), edit as text, write `{"content": {"$base64": text}}`.

## How to resolve this file

Delete it when a naive "append one line to README and open a PR" through the
live app lands a commit whose README differs from `main` by exactly the
appended line, with the run id, branch and commit sha recorded on the change.
