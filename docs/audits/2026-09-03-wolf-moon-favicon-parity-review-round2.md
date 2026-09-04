---

## EVIDENCE-BEARING REVIEW: TINYASSETS FAVICON/LOGO ROLLOUT

### 1. Canonical-source and generated-output coverage

**AGREE**

`WebSite/brand/render_marks.py` lines 243–274 define `_generated_paths()` and the provenance manifest enumerates 56 committed artifacts with SHA256 bindings. Coverage verified:

- **SVG sources** (mark.svg, mark-compact.svg, mark-tile.svg): lines 319–321, recorded in `generated-assets.json` lines 4–6
- **Website favicon/PWA** (favicon.ico, icon.svg, apple-touch-icon.png, icon-192.png, icon-512.png, site.webmanifest): lines 328–335, recorded lines 9–14
- **Repo brand assets** (assets/{icon,*-logo-*}.*): lines 338–344, recorded lines 22–23, 18–21
- **Desktop package icons** (tinyassets-app.{ico,icns}): lines 345–346, recorded lines 16–17
- **Tray** (tinyassets/desktop/app.ico): line 352, recorded line 54
- **Mobile icon + splash** (icon.png, splash.png): lines 268–269, recorded lines 52–53
- **Android density set** (mobile/resources/android/*.png): line 273 via rglob, recorded lines 26–51 (26 entries)
- **Play exports** (icon-512.png, feature-graphic-1024x500.png): lines 270–271, recorded lines 24–25
- **Served app** (tinyassets/onboarding/app.html): line 266, recorded line 55

All surfaces tied to one geographic source: `tinyassets/desktop/icon_gen.py` (line 295, recorded in `generated-assets.json` line 2).

---

### 2. Source-only changes and hand-edited outputs caught by unconditional CI path

**DISAGREE_EVIDENCE**

The brand parity test is defined in three places but runs only on manual deploy, not on every PR:

- `WebSite/site-react/package.json` line 14: `"test": "node --test scripts/*.test.mjs"` includes `brand-parity.test.mjs` (line 30–74)
- `tests/test_brand_parity.py` (lines 1–43) runs the same parity checks in Python
- **CI execution**: `.github/workflows/deploy-site-react.yml` line 66 runs `npm test`, but this workflow is **manual workflow_dispatch only** (lines 12–19). No pull_request trigger exists.

**Impact**: A commit changing `WebSite/brand/render_marks.py` (line 110–173) or `tinyassets/desktop/icon_gen.py` without regenerating outputs will **pass CI on the PR** and fail only during manual deploy. The `.github/workflows/invariants.yml` (lines 1–58) runs pre-commit-scoped invariants on pull_request (line 20) but does not include a brand-parity check—only cross_provider_drift, mirror_parity, mojibake, skills_valid, tab_single, context_budget (line 52–58).

---

### 3. Content-derived query versions break browser favicon and manifest caches and remain tied to generated mark

**AGREE**

Cache invalidation is correctly bound to the generated mark:

- `mark_version` is computed as SHA256 of all four SVG optical variants (lines 314–316 of render_marks.py), producing a 12-hex string like `ef7e1cdb0f17`
- Exported in `TinyAssetsMark.tsx` line 8: `export const TINYASSETS_MARK_VERSION = "ef7e1cdb0f17"`
- Used in `layout.tsx` line 15: `const markAsset = (path) => \`${path}?v=${TINYASSETS_MARK_VERSION}\`` 
- Applied to favicon.ico (line 24), icon.svg (line 25), apple-touch-icon.png (line 27)
- Applied to manifest URLs in site.webmanifest (render_marks.py line 157, 161, 167, 169)
- Verified in `brand-parity.test.mjs` lines 76–99: component exports match, layout.tsx has markAsset() calls, webmanifest icons carry the version query string

Any change to `icon_gen.py` geometry changes the SVG hash, changes the mark_version, updates all URLs with a new `?v=`, and browsers see a cache miss. ✓

---

### 4. Line endings, missing files, extra Android files, or generator changes can bypass receipt

**AGREE**

Bypass vectors are closed:

- **Line ending normalization**: Both generators and tests normalize CRLF→LF before hashing text files (`render_marks.py` line 281–282: `.replace(b"\r\n", b"\n")`; `test_brand_parity.py` line 15–16 same; `brand-parity.test.mjs` line 18 same)
- **Extra or missing Android files**: `test_brand_parity.py` lines 33–42 enforces exact set equality (`actual_android == recorded_android`). `brand-parity.test.mjs` lines 65–73 does the same with `assert.deepEqual()`. Adding or deleting an Android density PNG will fail both.
- **Generator changes**: Hashes of all three generators are recorded (`generated-assets.json` lines 57–60) and verified (`test_brand_parity.py` line 29; `brand-parity.test.mjs` line 42)
- **Missing files**: `render_marks.py` line 279 raises `SystemExit` if any expected generated file is missing during hash computation

No bypass found. Receipt is hermetic.

---

### 5. Desktop-app package icon paths are valid and tracked; Play feature-graphic update preserves type while refreshing mark

**AGREE**

- `desktop-app/package.json` lines 26, 33, 38 reference the generated icons:
  - Windows: `"../assets/brand/tinyassets-app.ico"` (tracked in `generated-assets.json` line 17, hash `962d542a686502c7...`)
  - macOS: `"../assets/brand/tinyassets-app.icns"` (tracked line 16, hash `93f83cd2268c8d82...`)
  - Linux: `"../assets/icon.png"` (tracked line 22, hash `48d3b31242c6eb57...`)
- All three are verified present in `brand-parity.test.mjs` lines 101–104
- **Play feature graphic** (`docs/ops/play-assets/feature-graphic-1024x500.png`): tracked in `generated-assets.json` line 24. `mobile/resources/README.md` lines 37–41 document that `--from-logo` mode (render_marks.py line 357) preserves the reviewed wordmark and deterministically updates only the logo panel, so feature-graphic type (PNG, 1024×500) stays stable while the mark refreshes.

---

### 6. Data-loss, scope, documentation/PLAN consistency; retired Svelte tree

**AGREE**

- **Scope is clean**: All modified files are in brand export / site infrastructure only. No daemon, storage, auth, or user-visible schema changes.
- **PLAN.md**: Updated with 1 line (shown in `git diff --stat`). Verified in PLAN.md excerpt—no conflict with design principles.
- **Retired Svelte tree**: `deploy-site-react.yml` lines 6–9 document that the old Svelte rollback tree and `deploy-site.yml` were retired 2026-09-02; rolling back now re-runs this workflow on an earlier revision. No data loss—git history holds prior site versions. **WebSite/PREVIEW.md and WebSite/DEPLOY.md**: Not read here, but the hardcoded note in the workflow confirms the Svelte retire is documented and closure is intentional.
- **No user-facing breaking changes**: The mark_version changes, but that's an intentional cache-invalidation mechanism, not a regression.

---

## SUMMARY

**Critical gap in CI enforcement** (section 2): The brand parity test does not run on pull requests. A developer who modifies `tinyassets/desktop/icon_gen.py` without running `python WebSite/brand/render_marks.py` will have a passing PR and a failing deploy. **Recommendation**: Add a PR gate that runs `npm run check:brand` in `WebSite/site-react/` unconditionally (no path filter), or add a pre-commit-scoped invariant.

Otherwise: source-of-truth binding is hermetic, cache invalidation is correct, desktop paths are valid, Android set parity is enforced, and spec consistency is sound.

---

**VERDICT: ADAPT**

*Rationale*: The architecture and implementation are sound, but ship this with a follow-up task: register a pre-commit invariant or add a PR-triggered test gate for brand parity (section 2), so a future commit changing `icon_gen.py` fails CI rather than a manual deploy step.
