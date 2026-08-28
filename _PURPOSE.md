# Worktree purpose

Purpose: worker-5xx-passthrough
Provider: claude-code
Branch: claude/worker-5xx-passthrough
Base ref: origin/main
Issue/PR: resolves docs/concerns/2026-08-28-worker-swallows-every-origin-5xx-body.md
PLAN refs: edge / public surface
Ship condition: a JSON 5xx from the origin reaches the caller with body and status
  intact; a non-JSON 5xx is still translated to bad_gateway; Hard Rule 11 canary green
  after the wrangler deploy
Abandon condition: n/a
Pickup hints: the Worker deploys via wrangler, NOT via deploy-prod.yml — landing the PR
  does not ship it
Memory refs: live-test-finds-what-tests-cannot
Related implications: docs/concerns/2026-08-28-stripe-4xx-reads-as-an-outage.md is the
  case this most benefits once fixed
Idea feed refs: (none)
