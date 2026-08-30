# Codex review — text-channel id leaks fixed at the emitters (branch `claude/text-channel-id-leak`)

Dispatched 2026-08-30 via `python scripts/peer_agent.py codex --prompt-file <brief>` on Codex's own budget. Round 1 pinned to 256efe7b (ADAPT); round 2 appended below when it lands.

## Round 1 (256efe7b): ADAPT

1. **DISAGREE_EVIDENCE** — `goal_bind`/unbind is clean: `tinyassets/api/market.py:1455-1469` renders only branch and Goal display names. However, `patch_branch` still leaks identifiers:

   - `tinyassets/api/branches.py:2990` prints `content_hash[:8]`. This is the stable version discriminator used to mint `branch_version_id` at `tinyassets/branch_versions.py:277`; the code itself says it “identifies the version” at `tinyassets/api/branches.py:2983-2984`. Under the text-channel rule, it belongs only in structured content.
   - A rejected `set_fork_from` patch embeds the full existing `branch.fork_from` at `tinyassets/api/branches.py:2815-2818`, then copies it into `text_lines` at `tinyassets/api/branches.py:2898-2923`.

   Command: targeted `pytest` passed both changed redaction tests, but a direct `_apply_patch_op` probe returned `full_branch_version_leaked=True`.

2. **DISAGREE_EVIDENCE** — additional uncovered emitters:

   - **Blocker, same claimed path:** rejected `patch_branch` described above. `test_patch_branch_text_hides_branch_def_id` only exercises the successful update path at `tests/test_text_channel_id_redaction.py:150-168`.
   - **Founder note:** `set_canonical` prints the complete `branch_version_id` at `tinyassets/api/market.py:2343-2354`.
   - **Founder note:** the create/remix `build_branch` invalid-`fork_from` fallback embeds `branch.fork_from` at `tinyassets/api/branches.py:2491-2498`, then joins it into text at `tinyassets/api/branches.py:2502-2514`.
   - Publish emits structured fields without a `text` field (`tinyassets/api/evaluation.py:875-881`); normal create/remix success uses `_build_branch_text` without the listed identity fields.

   Command: `rg -n '^def test_' tests/test_text_channel_id_redaction.py` shows no canonical, publish, remix, or rejected-patch coverage.

3. **AGREE** — on Linux, `iter_canon_files` resolves the symlink and skips it at `tinyassets/ingestion/canon_io.py:153-158`; both handlers then fall through at `domains/fantasy_daemon/phases/worldbuild.py:548-551` and `:617-620`. `_write_canon_file` resolves the same filename before writing at `:1077-1082`, raising exactly `canon filename escapes canon directory` from `tinyassets/ingestion/canon_names.py:24-28`. The assertions at `tests/test_universe_nodes.py:676` and `:698` require both `ValueError` and that phrase. The only production raise containing the phrase is `canon_names.py:28`, so an unrelated exception cannot satisfy them.

   Command: WSL2 Ubuntu stdlib probe using the exact `canon_io.py`/`canon_names.py` modules produced `enumerated=[]`, `ValueError: canon filename escapes canon directory: 'magic_system.md'`, and left the outside file unchanged.

4. **AGREE** — exactly four removals, zero additions, otherwise byte-identical. Command: `git diff --numstat origin/main...HEAD -- .github/known-failing-tests.txt` returned `0 4`; byte reconstruction reported `exactly_base_minus_four_lines=True`.

5. **AGREE** — `python scripts/invariants_run.py --check mirror-parity` returned `[OK] mirror-parity ... all 377 canonical file(s) mirror-matched`.

VERDICT: ADAPT 256efe7b — remove the short content hash from successful patch text; redact the existing `fork_from` ID from rejected patch text and cover both paths.
## Round 2 (6efa2186): ADAPT — one more emitter, delete the resolved concern

Evidence stamp: 2026-08-29, Windows 11 Home, PowerShell, Python 3.14.3, clean worktree at `6efa2186f0171de765e3c2d99f83389a7613d84e`.

1. **DISAGREE_EVIDENCE**

The four folded emitters are correctly redacted:

- Patch success says only “Version updated”; IDs remain outside `text` ([branches.py:2996](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2996)).
- Rejected immutable `set_fork_from` no longer names the existing ID ([branches.py:2815](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2815)).
- Both global and personal canonical strings omit the version ID ([market.py:2342](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/market.py:2342)).
- `build_branch`’s second `fork_from` validation emits a generic diagnostic ([branches.py:2496](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2496)).

However, another reachable rejection emitter on both `build_branch` and `patch_branch(add_node)` still leaks `branch_def_id`: a readable `node_ref.source` is normalized to the real branch ID ([branches.py:1613](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:1613)), then a missing referenced node embeds that ID in the error ([branches.py:1750](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:1750)). It flows into build text through [branches.py:2360](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2360) and [branches.py:2509](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2509), and patch text through [branches.py:2611](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2611) and [branches.py:2918](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2918).

Command: `rg -n -C 4 "resolved_source =|ref_source = resolved_source|_lookup_node_body|not found on branch|staging_errors|_apply_patch_op\(staging|text_lines.append" tinyassets/api/branches.py`

Topology node IDs/entry points intentionally remain in Mermaid/text; no goal, universe, principal, content-hash, or version identifiers remain in the four targeted composers.

2. **AGREE**

Structured identifiers remain:

- Patch: `branch_def_id`, `branch_version_id`, `content_hash`, and `parent_version_id` ([branches.py:3012](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:3012)).
- Rejected patch: the submitted operation, including its structured `branch_version_id`, remains in `errors[].op` ([branches.py:2896](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2896)).
- Canonical: `goal_id`, `scope_actor`, and `canonical_branch_version_id` remain structured ([market.py:2369](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/market.py:2369)).
- Build rejection retains raw `fork_from` in `attempted_spec` ([branches.py:2517](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2517)); successful build retains `branch_def_id` ([branches.py:2586](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:2586)) and actor/branch IDs in the receipt ([branches.py:1402](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tinyassets/api/branches.py:1402)).

Command: `git diff --unified=35 256efe7b..6efa2186 -- tinyassets/api/branches.py tinyassets/api/market.py`

3. **AGREE**

The four HEAD tests pass: `4 passed in 4.46s`.

Command: `python -m pytest -p no:cacheprovider --basetemp C:\Users\Jonathan\AppData\Local\Temp\tinyassets-review-6efa2186-7d393af37fc249398573fc58bcd3bb6a -q <four requested node IDs>`

They are non-vacuous and would fail against `256efe7b`:

- Old patch text emitted `content_hash[:8]`; the test now checks that exact prefix.
- Old rejected patch embedded `branch.fork_from`.
- Old canonical global/personal strings embedded the full `branch_version_id`.
- Old build rejection embedded the padded raw `fork_from`, which contains the asserted unpadded ID.

Command: `git grep -n -e "Published version" -e "fork_from is already set to" -e "Your canonical branch for Goal" -e "Canonical branch for Goal" -e "fork_from '" 256efe7b -- tinyassets/api/branches.py tinyassets/api/market.py`

The canonical test exercises only global scope (`scope` omitted at [test_text_channel_id_redaction.py:330](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/tests/test_text_channel_id_redaction.py:330)); the personal branch is correct by inspection but untested.

4. **AGREE**

The whitespace path is real on `origin/main`:

- Raw `fork_from` is retained during staging at line 2269.
- Pre-flight strips it at line 2461.
- Second validation submits the raw value at line 2494.
- `get_branch_version` performs exact SQL equality at `branch_versions.py:377`.

Command: `git show origin/main:tinyassets/api/branches.py | Select-String -SimpleMatch -Pattern 'fork_from=spec.get("fork_from") or None','fork_selector = (spec.get("fork_from") or "").strip()','get_branch_version(_base_path(), branch.fork_from)'`

Control flow, rejection status, and persistence behavior are unchanged. Beyond `text`, the shared structured `errors[]` string and `suggestions[].issue` are also redacted; `attempted_spec` remains unchanged.

5. **AGREE**

- `python scripts/invariants_run.py --check mirror-parity` → `[OK]`, all 377 canonical files mirror-matched.
- Exact sequence comparison: origin/main count 69, HEAD count 65, expected count 65, `exact_sequence_match=True`; precisely the four named entries were removed.
- Final `git status --short --branch` remained clean.

**DISAGREE_CONCERN:** [the concern file](/C:/Users/Jonathan/Projects/wf-text-channel-id-leak/docs/concerns/2026-08-30-text-channel-leaks-raw-ids.md:25) instructs deletion once the four quarantined tests are fixed and unquarantined, but it remains tracked at HEAD.

Minimal adaptation: redact the `node_ref.source` branch ID before it reaches both rejection texts and cover build/patch; delete the resolved concern.

VERDICT: ADAPT 6efa2186
## Disposition: shipped after two rounds as PR #2705 (head c21ede89, rebased on 9b15dd27). Both ADAPT lists were folded with tests red on the prior sha; the third round was not spent on a bug-fix lane. Codex's remaining founder note: topology node ids and entry points intentionally stay in Mermaid/text.
