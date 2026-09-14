# Implementation slice: inert source projects

Date: 2026-09-14. Proposal approval: [follow-up review](https://github.com/Jonnyton/TinyAssets/pull/3840#issuecomment-5672004803), reviewed head `23b6e41959828eac92ca7116259e16b73b90fe3b`.

## Implemented boundary

`tinyassets.agent_project.export_project` packages an explicitly supplied native
definition and UTF-8 source map. `inspect_project` validates the complete package
in memory and returns an inert receipt. No directories are traversed or created;
no code, dependency, provider, binding or pending request is activated. This is a
library adapter beside the existing native/interchange modules, not a new registry
or public MCP action. The root location follows those domain siblings.

The text-only profile is `tinyassets-source-project/v1`. Its encoded JSON is
bounded by the existing interchange `MAX_SOURCE_BYTES` (1 MiB), including envelope
overhead. This is the current transport's limit, not a proposed package-size ceiling
for all future transports. Binary assets and larger workspace artifacts remain
unsupported by this profile. Files are explicit strings, so link entries are
unrepresentable; paths reject traversal, drive/UNC/backslash paths, non-NFC names,
case-fold collisions, reserved device names, and file/directory collisions.

`agent.json` uses the existing native normalization and fingerprint. Other source
bytes are retained exactly. The lock covers path, UTF-8 byte length and SHA-256.
The project digest uses RFC 8785-compatible JSON for a **closed metadata grammar**:
ASCII object keys (including validated entry names), strings, arrays and bounded
integer byte counts. Arbitrary native JSON is not passed through this codec. A
Node cross-language test independently rebuilds inventory from source files and
checks Unicode, escaping, byte counts and the digest. Inventory order is Unicode
code point order, equivalent to UTF-8 byte order for valid paths. In particular,
`src/\uFFFD.txt` precedes `src/\U0001F600.txt`; JavaScript default UTF-16 `.sort()`
is not the inventory ordering contract.
Extending metadata to arbitrary keys/numbers requires the existing pinned
`rfc8785` dependency and additional vectors; this restricted codec is not a
general replacement for that dependency.

Unknown native component kinds survive byte-preserving round-trip. Runtime
requirements are retained, never treated as grants or satisfied by name. Inspection
always reports `executable: false` and unknown runtime compatibility. Source
credential detection reuses the native checks, gives value-free diagnostics, and
is defense in depth: explicit source selection cannot prove arbitrary text contains
no secret.

## Verification and limits

Run `python3 -m unittest discover -s tests -p test_agent_project.py -v`.
The cases cover round-trip, altered source, tampered locks and inventories, inert
source containing a deliberate exception, path collisions, private content,
unsupported representations, missing entries, encoding and transport budgets.
The cross-language case requires Node. It fails in CI if Node is absent, so this
proof cannot silently skip there; local environments may explicitly skip it.
The current `tests.yml` uses `ubuntu-latest` without an explicit Node setup step;
this test enforces availability rather than assuming the runner image supplies it.

The governed Linux workspace lacks pytest, Ruff, the OpenSpec CLI and full runtime
dependencies. The dependency-free unittest suite and Node digest check are the
available local evidence; CI lint/full-suite results and the plugin import probe
remain required before landing. Plugin source is regenerated with the documented
minimal-environment `--skip-probe` option. This commit stays draft.

## Next execution boundary

The actual first-party entry point is
`tinyassets.shared_self.prepare_shared_self_turn`: it reads the current founder
home, builds the persona/history through `universe_intelligence`, and uses the
same sandboxed engine configuration as conversation. `universe_self` is currently
declared by one immutable owner-authored prompt node. Its stored owner and provider
admission remain authoritative. This package inspector neither replaces that
composition nor bypasses it.

Next: map inventoried source to real Branch nodes, run the offline fixture in
the Linux code sandbox with node/effect evidence, then demonstrate replacement of
the served outer composition through ordinary bindings. Windows must report
unavailable sandbox capability. CLI inner-loop limits remain a current adapter
limitation, not the product ceiling. Browser staging, dependency closure,
second-account binding, live whole-harness replacement and shared S-1 adoption
remain open. No partial conformance case is marked complete on this library proof.

## Implementation review follow-up (2026-09-14 UTC)

The [retained review](review-evidence.md) approves the first inert slice at
`0a3b47c37277c7c21b8e9898bb69f0364c56e1ad`, with two required small fixes.
This follow-up rejects overflowing JSON numbers (including `1e400`) through
`ProjectValidationError` and distinguishes malformed JSON source from detected
private content. Regression cases cover both exponent signs, JSONC and duplicate
keys. Strict JSON remains required for `.json` files; JSONC is not silently accepted.
The native normalizer remains the sole portable-key source: export compares input
keys with normalized output instead of maintaining a second field set.

The source secret scan remains heuristic defense in depth; credential-shaped
comments may be refused. That limitation is accepted for this inert profile,
not a claim of complete secret discovery. The approval comments are retained
alongside this change; the fixes do not turn the older exact-head review into
an approval of a new head. Full CI and execution/adoption evidence remain open.
