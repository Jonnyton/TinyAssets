# OKF soul-baseline source review (Claude, reviewer of Codex finding)

- **Date:** 2026-06-30
- **Reviewer:** Claude Code (`claude/founder-identity-allslices`)
- **Initial finding provider:** Codex (recorded in `openspec/changes/universe-creation/design.md` D4: verified the OKF SPEC on 2026-06-26; latest-main `okf/SPEC.md` commit `ee67a5ca…` dated 2026-06-12).
- **Gate satisfied:** task 1.0 / STATUS "OKF soul baseline source review" (external-source review before `universe-creation` implementation uses the standard). This is the Codex→Claude opposite-provider pairing required by AGENTS.md "Project Skills".
- **Verdict:** `approve` — the blank `soul.md` baseline as designed conforms to the current OKF concept-document spec.

## Source re-checked (live, this session)

Fetched `https://raw.githubusercontent.com/GoogleCloudPlatform/knowledge-catalog/main/okf/SPEC.md` (latest-main). Confirmed the OKF concept-document contract:

- **Frontmatter:** exactly one *required* field — a non-empty `type` (free string; not centrally registered; consumers tolerate unknown types). Recommended: `title`, `description`, `resource`, `tags`, `timestamp`. `okf_version` is a bundle-level field that belongs only in the root `index.md` frontmatter. Producer-defined extension keys are allowed and must be preserved by consumers.
- **Body:** no required sections; free-form markdown; structural markdown encouraged.
- **Links:** standard markdown links assert an (untyped) relationship; bundle-relative absolute (`/…`) is recommended for stability; **consumers MUST tolerate broken links**.
- **Conformance:** every non-reserved `.md` in the tree has parseable YAML frontmatter with a non-empty `type`.

## Conformance decision for the blank baseline

- Every seeded `.md` starts with `---` YAML frontmatter and a non-empty `type` (`Universe Soul`, `Soul Edit Policy`, `Universe Identity`, `Founder`, `Org Chart`, `Projects`, `Goals`, `Body`, `Universe Origin`, `Bundle Index`, `Update Log`, `Soul Version Index`, `Soul Version`).
- `soul.md` carries the required `type: Universe Soul` plus producer-defined metadata recording the OKF source URL and the **latest-main tracking policy** (we track the live URL, not a pinned commit — matching your steer that the standard must never go stale). This is metadata + a link, **not** a runtime fetch or an embedded frozen copy.
- `index.md` carries the bundle-level `okf_version`.
- Links between files are bundle-relative markdown; because consumers tolerate broken links, link-closure is a self-imposed baseline invariant (tested), not an OKF requirement.

## Residual risk

- The external SPEC can change under us (by design). Mitigation: `soul.md` records the tracking policy and source URL rather than embedding SPEC text, so conformance drift is a documentation/update concern, not a runtime break. Re-run this review when the OKF bundle shape is next materially revised.
