# Retained independent review evidence

Source: https://github.com/Jonnyton/TinyAssets/pull/3840 (comments posted 2026-09-14 UTC).
Copied from GitHub for durable provenance. These are reviewer-authored statements,
not additional founder instructions. Proposal approval and implementation approval
apply to their explicitly named heads; they do not certify later fixes or deployment.

## Posted 2026-09-14T23:05:10Z

```text
# Follow-up Fable 5.1 proposal review: APPROVE for implementation

Independent third-round review completed September14,2026,227seconds, on exact
heads3840=`23b6e41959828eac92ca7116259e16b73b90fe3b` and
3842=`5e8a5d0120566b4c49b56e6a81388e35bb1a818d`.
**PR3840 VERDICT: APPROVE. PR3842 VERDICT: APPROVE.**

These are proposal approvals to proceed with implementation, **not claims that
either feature is implemented, merged, deployed or live-tested**. All five
posted harness findings and all six experience findings are addressed at the
proposal level. The shared S-1 acceptance trace is identical and covers UI-only,
harness-only, entire-setup and mixed adoption while retaining the receiver's
data/customizations and excluding the publisher's credentials and authority.

Carry these bounded points into implementation; they do not require another
proposal-review loop:

- Ground first-party harness replacement in the current served composition,
  including `prepare_shared_self_turn`/`universe_self`, not merely the component
  descriptor compiler. Outer loop/tool composition is an available first slice;
  the current CLI's inner-loop limitation is **not** a permanent product ceiling
  or proof that the full harness-replacement requirement is complete.
- Execute offline code fixtures in the Linux sandbox; Windows must truthfully
  report unavailable sandbox capability rather than simulate a passing run.
- Bind prepared UI intent to typed operations. Do not attach automatic Retry to
  a relayed conversation message without an action identity.
- Reword the residual "Memory policy may propose writes" sentence so ordinary
  already-authorized learning is not gated; cite the actual Android/Play state
  and keep phone push/earbud/native-device proof distinct from a rendering shell.

The research comparison, materialization boundary, source-specific cursors,
pending-request reuse, renderer confinement, retained customization and external
effect uncertainty are now sufficient to start building. Required runtime and
rendered acceptance evidence remain implementation tasks, not reasons to leave
the proposals indefinitely awaiting confirmation. The universe agent remains
the implementation owner; no private workflow or project source was edited by
the reviewing operator.

```

## Posted 2026-09-14T23:37:27Z

```text
The Stop hook lists dispatch outputs in the author's private worktree 0a7f. Per your instruction those are unrelated shared-ledger jobs outside this review's scope, so I am not reading or acting on them. Repeating the entire deliverable as requested.

# Fable 5.1 first-implementation review, 2026-09-14

Constraints honored: no subagents, no Codex or peer process, no worktrees, no edits, one test file per PR. Evidence gathered on Windows 11, Python 3.14, Node present, at the exact heads below. Browser render of the preview fixture was permission-denied, so it stays unverified.

## PR3840 head `0a3b47c37277c7c21b8e9898bb69f0364c56e1ad` (parent `23b6e41959828eac92ca7116259e16b73b90fe3b`)

Scope: new `tinyassets/agent_project.py`, `tests/test_agent_project.py`, plugin mirror, `implementation.md`, one `primitives.md` paragraph, one `tasks.md` check-off. Mirror is byte-identical (`cmp`). `python -m unittest tests.test_agent_project -v`: 8 pass, and the Node cross-language digest case actually ran here rather than skipping.

- **AGREE, determinism.** Export is insertion-order independent (reproducer: same sources in two orders produce identical bytes), inventory is sorted, the round-trip test asserts byte-equal re-export, and the closed-grammar digest at `tinyassets/agent_project.py:144-154` matched an independent Node canonicalizer on a Unicode/astral fixture.
- **AGREE, preservation.** Unknown component kinds survive export→inspect→export; non-`agent.json` bytes are retained exactly; editing a source changes `project_digest` while `native_fingerprint` holds.
- **AGREE, rejection boundaries.** Traversal, backslash, drive, NFC, case-fold, reserved device, file/dir collision, tamper of files or lock, `bytes: true`, duplicate keys, `NaN`/`Infinity`, binary values, budget, and `agent.json` override all refuse with value-free `ProjectValidationError`.
- **AGREE, no false executable or authority claim.** Receipt hard-codes `executable: False` and `runtime_requirements_satisfied: None` (`:231-235`); `_NATIVE_KEYS` refuses stored rows carrying ids or bindings (`:178-179`).
- **AGREE, no execution or network on inspection.** The module source contains no `subprocess`, `importlib`, `open(`, `socket`, `urllib`, `exec(`, `eval(` or `os.` token; the test's `raise RuntimeError` source never fires.
- **DISAGREE_EVIDENCE, wrong exception type escapes (minor).** `agent_project.py:225` canonicalizes the untrusted lock; `parse_constant` at `:52` only intercepts the literal `Infinity` token, so an overflowing `1e400` parses to `inf` and `AgentValidationError("payload must be JSON-compatible: ... inf")` escapes instead of `ProjectValidationError`. Reproducer: export any package, replace `lock.inventory[0].bytes` with `1e400` in the raw text, call `inspect_project`. A future handler catching `ProjectValidationError` would 500. One-line fix: wrap the lock comparison like `:113`, or pass a `parse_float` that refuses non-finite.
- **DISAGREE_EVIDENCE, misleading diagnostic (minor).** `agent_project.py:110-114` parses every `.json` source strictly inside the secret-scan try block, so a JSONC `tsconfig.json` or a duplicate-key `.json` file is refused as "source contains forbidden private content". Reproducer: `export_project(n, sources={"tsconfig.json": "{// c\n}"})`. Either scan raw text only for non-strict JSON, or move `_json` outside that except and report "invalid JSON source file".
- **DISAGREE_CONCERN, inventory order is code-point order.** Reproducer: `U+FFFD.txt` sorts before `U+1F600.txt`; a JS producer using default `.sort()` (UTF-16 units) orders them oppositely and would be refused as "inventory mismatch". The Node test takes inventory as given, so ordering is untested. State "code point / UTF-8 byte order" in `implementation.md` and add that vector. Non-blocking while Python is the only producer.
- **DISAGREE_CONCERN, two definitions of one fact.** `_NATIVE_KEYS` (`:26-29`) re-declares the output key set of `_normalize_definition_payload` (`custom_agents.py:422-430`). A new native key would be silently refused by export. Derive from a shared constant. Non-blocking.
- **DISAGREE_CONCERN, heuristic secret scan false positives.** A comment containing `Bearer abc` refuses the whole package; documented as defense in depth, acceptable for an inert slice.
- **DISAGREE_CONCERN, approval artifact off-branch.** `tasks.md` checks off the approval by head sha and PR comment; the review file exists at 0a7f commit `809cd007` but is on neither PR branch. Land it alongside so the gate is an in-repo artifact.
- **Tests: meaningful.** Tamper and path matrices, value-free diagnostic assertions, and a real cross-language digest. Confirm Linux CI has Node so the cross-language case is not silently skipped there.

## PR3842 head `c3a7d2a137dbd876dd716bd7fc59db1596b43920` (parent `5e8a5d0120566b4c49b56e6a81388e35bb1a818d`)

Scope: new `tinyassets/onboarding/experience.js`, `tests/test_experience_preview.cjs`, `examples/experiences/preview.html`, mirror, `implementation.md`, one `tasks.md` check-off. Mirror byte-identical. `node --test`: 6 pass; `node --check` clean.

- **AGREE, preview confinement and text safety.** Every string reaches `textContent` (`experience.js:113`); tag names are fixed; `className` is limited to the validated `board|list` (`:122,:129`); no `innerHTML`, `insertAdjacentHTML`, or attribute set from user data. The DOM double traps `innerHTML`. Fixture CSP is `default-src 'none'; connect-src 'none'; img-src 'none'`.
- **AGREE, not wired into the served app.** `serving.py` and `app.html` contain no reference to the script; only the `__init__.py` docstring mentions "experience".
- **AGREE, stale exact-intent.** `prepareIntent` freezes canonical source, input, target and revision (`:85-89`); `revalidateIntent` re-prepares and compares canonical strings (`:95-97`), so changed source, input, target, revision, or an injected `retry: "automatic"` all refuse. Tests exercise each.
- **AGREE, no conversation retry masquerading as typed retry.** `recovery` (`:100-104`) always returns `automaticRetry: false`; `kind === "conversation"` wins over a fabricated `actionId`; `converse` as an operation is refused at prepare (`:74-75`).
- **AGREE, no false authority.** `executable: false`, `admission: "not_requested"`, `retry: "unsupported"`; the `:92-93` comment correctly disclaims client-side comparison as authorization. Forbidden keys include `universe_id`, `branch_id`, `run_id`, so private identifiers cannot ride in shareable source.
- **DISAGREE_CONCERN, fixture never rendered.** `implementation.md` says no browser was available, and my attempt was denied. The open question is whether `script-src 'self'` on a `file://` document permits the relative `<script src>`; if not, `TinyExperience` is undefined and the page shows only the error line. One real-browser console capture at desktop and phone widths closes this. Not a landing blocker for a dark example file, but it is the slice's only rendered claim.
- **DISAGREE_CONCERN, minor.** `recovery` treats any outcome with an `actionId` and a kind other than `conversation` (including a missing kind) as a typed action outcome (`:101-103`). Require an explicit `kind === "action"` so unlabeled outcomes default to canonical history.
- **DISAGREE_CONCERN, minor.** The credential regex at `:47` is case-sensitive and narrower than Python's `_CREDENTIAL_VALUE` (`custom_agents.py:85-89`): two definitions across languages. Fine for a preview; note before any shared import path.
- **DISAGREE_CONCERN, minor.** Non-array `options.fixtures` throws a raw `TypeError` at `:130`; the HTML always passes an array.
- **Tests: meaningful,** and honest that the DOM double is not browser evidence.

## Scope statement

Both are honest inert first slices. Neither is, nor claims to be, a harness or UI replacement, source execution, native import staging, device proof, or S-1 retained-data adoption. Those remain explicitly open and are not held against these PRs.

**PR3840 VERDICT: APPROVE** with two trivial in-slice fixes (escaped `AgentValidationError` on non-finite lock numbers; misleading diagnostic for malformed `.json` sources) to apply before merge without a further review round.

**PR3842 VERDICT: APPROVE** with one ask: attach a real-browser render capture of `preview.html` at desktop and phone widths, since that is the slice's only rendered claim and it is unverified by both author and reviewer.

```
