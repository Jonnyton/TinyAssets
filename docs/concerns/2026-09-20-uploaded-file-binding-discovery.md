# Uploaded attachment cannot be processed through ordinary agent use

September20,2026, deployedf020bf26. Primary app paperclip accepted public PNG
(47047bytes,512x512,SHA25648d3b31242c6eb570cb4f5209ec3016bc282f67a42e0143c56ef4fb42f5a6fa1).
Natural request for pixel dimensions/checksum returned metadata only and
run_file_refused, because read requires a run-bound file. User-style approval
to build its own workflow then produced dimensions from GitHub contents API,
NOT the uploaded bytes. Root did not count that as acceptance and asked whether
the agent can process the actual attachment or identify its concrete blocker.
Reply stamped16:50PDT says capture needs authoring session/handle and it has no
operation accepting the attachment file_id. No operator workflow or binding edit.

Independent root source check in deployed-equivalent release tree5a6d1347:
api/run_files.py dispatch_file_branch already binds declared file inputs through
reserve_direct_run. Engine run_graph forwards inputs_json, but its docstring
only says optional JSON run inputs and has no app-reference binding description.
write_graph describes authoring capture; the app sends exact versioned refs in
an untrusted metadata block. Existing as-built run-file-inputs spec says graph
admission accepts same-owner refs. Hypothesis: discoverability/schema guidance
gap, not evidence a new binding primitive or weaker unbound reads are required.
Need independent diagnosis of served authoring/run descriptions and actual
contract shape before fix. Keep current read/run/owner fences; no public URL,
direct-byte bypass or developer-created workflow as acceptance workaround.

Acceptance remains actual uploaded-byte processing by the app agent through its
own ordinary tools, not matching metadata or a same-named external copy. If
staging expires before release, a fresh ordinary upload is needed and must not
be reported as proof of the expired upload. Free-only account remains held.

## Status 2026-09-20 (branch codex/app-file-binding-guidance)

Independent shape review (APPROVE) and root source check agreed: the runtime
path exists end-to-end; the gap was the advertised tool descriptions. Landed on
this branch, no runtime change:

- served engine and connector `read_graph`/`write_graph`/`run_graph`
  descriptions now state that an app attachment is already a six-field
  reference binding VERBATIM through `run_graph inputs_json` into a declared
  `io_manifest` file input; capture is only for authoring handles; the
  delivery-only file refusal is scoped to `operation=deliver_output`; the CODE
  NODES text distinguishes "no ambient filesystem" from the authorized
  `read_run_file` RPC over bound inputs, with a working create recipe.
- `tests/test_app_file_upload_run.py`: registered descriptions carry the
  recipe (red on the old docstrings, both servers), and a real authenticated
  ASGI upload -> served create -> `run_graph` -> exact digest + first 16 bytes
  -> bounded `read_graph` export, with foreign owner/home and forged
  references still refused with zero runs reserved.
- `openspec/specs/run-file-inputs/spec.md` discoverability requirement and
  scenario.

Remaining before this file is deleted: deployed sha contains the commit, and a
rendered live conversation in which an uncoached app agent processes a fresh
ordinary upload's actual bytes (dimensions from the PNG, not the GitHub copy,
not the reference metadata). No `suggested_action` response field was added;
that review suggestion is deferred and is not required for acceptance.
