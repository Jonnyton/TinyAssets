# Hosted Preview Bootstrap Verification

Freshness: 2026-07-27 America/Los_Angeles, Windows 11 host,
`origin/main`-based worktree `wf-preview-boundary-bootstrap-20260727`.
Implementation/evidence anchor: `6d01e2cc` (`fix(preview): close residual
discovery edges`); tree:
`ddb9ebf1cba9349b08fe45d0731a54f62b9b9a86`. The credentialed `workflow_run`
consumer cannot run until its trusted definition lands on the default branch.

## Source Verification

| Check | Command | Result |
|---|---|---|
| Preview contract + hostile validators | `cd WebSite/site; npm ci; npm test` | 201 total; 197 passed, 0 failed, 4 Windows capability skips |
| Linux zero-skip merge gate | GitHub `preview-security` run `30325900272`, Ubuntu 24.04, PR #1823 head `6e96cff0` | 201 passed, 0 failed, 0 skipped; run succeeded |
| Design system build | `cd WebSite/design-system; npm ci; npm run build` | passed; 123 tokens and 6 component schemas generated |
| React static export | `cd WebSite/site-react; npm ci; npm run build` | passed; 26 static routes |
| Trusted deployment toolchain | `cd WebSite/site-react/preview-deploy-tools; npm ci --ignore-scripts --no-audit --no-fund; npm exec --no -- wrangler --version; npm audit --omit=dev` | Wrangler `4.114.0`; 0 vulnerabilities |
| Workflow syntax | pinned actionlint 1.7.7 over `preview-security.yml`, `preview-worker.yml`, and `preview-worker-deploy.yml` | passed |
| Workflow security lint | `uvx zizmor==1.28.0` over all three workflows with authenticated GitHub metadata | no findings; one justified `workflow_run` dangerous-trigger suppression |
| OpenSpec | strict validation of canonical `public-website-surface` plus unsynced `activate-hosted-preview-publication` successor after source archive | both valid; source archived at `openspec/changes/archive/2026-07-27-harden-hosted-preview-trust-boundary/` with 12/12 tasks checked |
| Parsed target/authority scan | `preview-worker-security.test.mjs` over all three workflows and trusted Worker/config/tool lock | passed |
| Deployed-tree receipt | fixed SHA-256 fixture over the exact pretty-JSON manifest bytes; byte, path, and ordering mutations | expected digest matched; every mutation changed it |
| Worker routing matrix | dynamically imported trusted Worker with an ASSETS spy; 47 literal/case/slash/dot/encoded/double-encoded/malformed MCP, OAuth/OIDC/MCP-discovery, empty-segment, and residual-percent paths plus 4 benign paths | every blocked path returned no-store `503` with zero ASSETS calls; unrelated `.well-known` and ordinary paths delegated once |
| Wrangler command parse/bundle | pinned Wrangler `versions upload ... --preview-alias p16-r5m-a3 --experimental-provision=false --experimental-auto-create=false --dry-run` | passed; assets binding recognized |
| Wrangler receipt parser | `validate-preview-upload.test.mjs` against the exact 4.114.0 labels/URL shapes plus hostile duplicates, controls, hosts, aliases, and subdomains | passed |
| GitHub head-shape audit | `gh api` for current run `30316290900` and prior PR #1812 runs | current `head_sha`, associated head, and PR head agree at `287049e1`; historical run heads remain old while associated heads drift current |
| Exact diff/status | `git diff --check 44694b1d..6d01e2cc`; `git status --porcelain`; `docview.py stat STATUS.md` | final implementation diff clean; only this evidence update remained when captured; STATUS exactly 60 lines |

The representative React export contained 111 files, 54 directories,
165 total entries, 2,861,047 uncompressed bytes, maximum depth 6, and a longest
relative path of 59 Unicode characters / 59 UTF-8 bytes. Those measurements are
well inside the 25 MiB compressed archive, 10,000-file, 2,000-directory,
12,000-entry, depth-32, 512-character / 1,024-byte path, 25 MiB per-file, and
250 MiB expanded-total limits.

The four skipped validator fixtures require filesystem capabilities Windows did
not expose to the test process: a newline-bearing filename, a control-character
filename, POSIX-executable mode bits, and symlink creation. Hard-link creation
worked and its rejection fixture passed on this Windows run. The four skipped
rejection paths were not runtime-exercised on Windows. Linux
`preview-security` run `30325900272` exercised the full suite with 201 passes
and zero skips, satisfying the platform-specific merge gate.

## Findings Kept Open

- Dependency installation reported inherited audit findings: React 1 critical
  and 1 high, Svelte 7 high, and design system 2 high. `STATUS.md` records this
  as a P0 upgrade/reachability concern; this bootstrap does not conceal or
  auto-fix unrelated dependency upgrades.
- Same-repository contributors can edit other workflows to request the
  repository's 19 repository-level secrets. This preview workflow references
  none of them, but repository-wide credential custody remains a separate P0.
- No dedicated-account/environment activation evidence is recorded. Live
  publication remains blocked. The strict-valid
  `activate-hosted-preview-publication` successor owns the dedicated account,
  inert host-created alias/version, base/alias/version Access proof, protected
  environment, and first live publication; it stays unsynced until those
  external facts are true.
- Rendered hosted-preview and post-fix organic-use evidence remain unavailable
  until the bootstrap lands and PR #1812 is rebased onto it.
- PR closure and GitHub artifact expiry do not delete Cloudflare versions.
  Activation therefore requires deny-by-default Cloudflare Access; alias
  mappings age out after the newest 1,000, while underlying immutable version
  URLs remain Access-controlled retained evidence.

## Independent Review

- Three Codex lanes approved the pre-adaptation source at `3913c84b`.
- Claude Opus 5 reviewed that exact tree and returned `CONCERNS`: the comment
  treated GitHub's warning-only API archive digest as verified provenance;
  selective Worker-first routing had undocumented normalization; preview/evidence
  wording overstated merge checks and skipped-test coverage; an unresolved
  Castles P1 had been removed; and Access proof omitted the base `workers.dev`
  origin.
- `8e4fb99b` adapts every source/document concern: exact artifact ID plus a
  protected-job digest of the regenerated byte-identical manifest; unconditional
  Worker-first with canonical/fail-closed MCP-equivalent routing; explicit
  base/alias/version Access proof; accurate test wording; and restored P1.
- Claude Opus 5 then reviewed exact head `a204d96e` and found no implemented
  security defect, but required source/activation OpenSpec lifecycle separation,
  a durable host-action row, and narrower wording. It also identified unblocked
  MCP discovery paths and accepted-but-unservable literal-percent artifacts.
- `753e3763` adapts those findings: a dormant source-only change; an unsynced
  activation successor with inert host-created alias/version ordering; restored
  host coordination; blocked OAuth/MCP discovery namespaces; literal-percent
  rejection; pinned static-asset routing; and corrected head-recheck wording.
- An exact-head Codex lifecycle review of `70152f3f` caught one successor-only
  contradiction: the account inventory forbade all credentials while the inert
  upload required a host-held credential. `81912aa0` now forbids production
  credentials while permitting exactly one least-privilege preview-only
  host-held bootstrap credential outside GitHub until Access proof is accepted.
- Three exact-head Codex lanes and Claude Opus 5 approved `44694b1d` for the
  dormant source merge. Opus left only non-blocking defense-in-depth notes:
  empty-after-dot/space segments fell through to an unreachable 404, OIDC
  discovery was not explicit, and GitHub may materialize an empty environment
  before activation.
- `6d01e2cc` closes those notes: empty-after-normalization segments fail closed,
  `/.well-known/openid-*` joins the blocked discovery surface, fixtures pin both,
  and operator/successor guidance says to create or harden the possibly
  pre-existing empty environment only after Access proof.
- Three exact-head Codex lanes and Claude Opus 5 approved `e16f7bf0` after
  independently reproducing the 201-test totals, strict validation, routing
  counts, evidence anchor, and source/activation split. The source-only
  OpenSpec-generated archive/sync diff still requires final exact review.
- `9c0fedd4` synced only the source requirement into canonical
  `public-website-surface`, archived the source change with 12/12 tasks checked,
  and left `activate-hosted-preview-publication` active and unsynced with all
  host/live-evidence tasks open.
- Three exact-head Codex lanes and Claude Opus 5 approved the generated
  archive/sync at `c2e5e4a0`: the canonical addition is byte-identical to the
  archived delta body, no source boundary file changed after approval, and
  activation remains active, unsynced, and 0/15.
