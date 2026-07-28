# Hosted Preview Bootstrap Verification

Freshness: 2026-07-27 America/Los_Angeles, Windows 11 host,
`origin/main`-based worktree `wf-preview-boundary-bootstrap-20260727`.
Implementation anchor: `3587770c` (`fix(preview): bind immutable trusted
publication`). Exact reviewed evidence head: `3913c84b`; tree:
`4940caa7eff9c629b51a9aa553edc014d7d542aa`. The credentialed `workflow_run`
consumer cannot run until its trusted definition lands on the default branch.

## Source Verification

| Check | Command | Result |
|---|---|---|
| Preview contract + hostile validators | `cd WebSite/site; npm ci; npm test` | 146 total; 142 passed, 0 failed, 4 Windows capability skips |
| Design system build | `cd WebSite/design-system; npm ci; npm run build` | passed; 123 tokens and 6 component schemas generated |
| React static export | `cd WebSite/site-react; npm ci; npm run build` | passed; 26 static routes |
| Trusted deployment toolchain | `cd WebSite/site-react/preview-deploy-tools; npm ci --ignore-scripts --no-audit --no-fund; npm exec --no -- wrangler --version; npm audit --omit=dev` | Wrangler `4.114.0`; 0 vulnerabilities |
| Workflow syntax | pinned actionlint 1.7.7 over `preview-security.yml`, `preview-worker.yml`, and `preview-worker-deploy.yml` | passed |
| Workflow security lint | `uvx zizmor==1.28.0` over all three workflows with authenticated GitHub metadata | no findings; one justified `workflow_run` dangerous-trigger suppression |
| OpenSpec | `openspec validate harden-hosted-preview-trust-boundary --strict` | valid |
| Parsed target/authority scan | `preview-worker-security.test.mjs` over all three workflows and trusted Worker/config/tool lock | passed |
| Wrangler command parse/bundle | pinned Wrangler `versions upload ... --preview-alias p16-r5m-a3 --experimental-provision=false --experimental-auto-create=false --dry-run` | passed; assets binding recognized |
| Wrangler receipt parser | `validate-preview-upload.test.mjs` against the exact 4.114.0 labels/URL shapes plus hostile duplicates, controls, hosts, aliases, and subdomains | passed |
| GitHub head-shape audit | `gh api` for current run `30316290900` and prior PR #1812 runs | current `head_sha`, associated head, and PR head agree at `287049e1`; historical run heads remain old while associated heads drift current |
| Exact diff/status | `git diff --check 3587770c..3913c84b`; `git status --porcelain`; `docview.py stat STATUS.md` | exact commit diff clean; worktree clean when evidence was captured; STATUS exactly 60 lines |

The representative React export contained 111 files, 54 directories,
165 total entries, 2,861,047 uncompressed bytes, maximum depth 6, and a longest
relative path of 59 Unicode characters / 59 UTF-8 bytes. Those measurements are
well inside the 25 MiB compressed archive, 10,000-file, 2,000-directory,
12,000-entry, depth-32, 512-character / 1,024-byte path, 25 MiB per-file, and
250 MiB expanded-total limits.

The four skipped validator fixtures require filesystem capabilities Windows did
not expose to the test process: newline/control-character filenames,
POSIX-executable mode bits, and symlink creation. Those four rejection paths
were not runtime-exercised on Windows; Linux CI with zero skips remains required
merge evidence.

## Findings Kept Open

- Dependency installation reported inherited audit findings: React 1 critical
  and 1 high, Svelte 7 high, and design system 2 high. `STATUS.md` records this
  as a P0 upgrade/reachability concern; this bootstrap does not conceal or
  auto-fix unrelated dependency upgrades.
- Same-repository contributors can edit other workflows to request the
  repository's 19 repository-level secrets. This preview workflow references
  none of them, but repository-wide credential custody remains a separate P0.
- No dedicated-account/environment activation evidence is recorded. Live
  publication remains blocked until the host creates the dedicated preview
  account, `workers.dev` subdomain, fixed Worker, Access policy, and protected
  environment settings, then proves anonymous denial and authorized review.
- Rendered hosted-preview and post-fix organic-use evidence remain unavailable
  until the bootstrap lands and PR #1812 is rebased onto it.
- PR closure and GitHub artifact expiry do not delete Cloudflare versions.
  Activation therefore requires deny-by-default Cloudflare Access; alias
  mappings age out after the newest 1,000, while underlying immutable version
  URLs remain Access-controlled retained evidence.
