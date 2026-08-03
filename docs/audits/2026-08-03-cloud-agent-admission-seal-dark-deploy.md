# Cloud agent admission-seal dark deployment

Freshness: 2026-08-03, GitHub-hosted Ubuntu runner plus the production Linux
host, merged revision `81c01fa721afa6c29177de32d48b8f77c4e09419`.

## Classification

This is live dark-deployment evidence for the generic cloud-agent foundation.
It is not evidence that an ordinary repository-to-spec Branch is registered,
claimable, or producing useful progress. It also does not satisfy rendered
chatbot control, tray-to-cloud cutover, post-fix organic use, or the 24-hour
PC-off acceptance gate.

## Immutable delivery

- PR #2178 merged revision `81c01fa721afa6c29177de32d48b8f77c4e09419`.
- Build run `30776900849` published immutable image digest
  `sha256:d4ef634076309b18f369da2584667ed83abccfc5fef5501f91171494026e320a`.
- Production deploy run `30777056289`, attempt 2, completed successfully at
  2026-08-03T01:38:16Z.
- The first attempt was cancelled during the stop-writer preflight. Its durable
  evidence showed `current_run_cutover_started=false`; no production runtime
  or cutover mutation occurred. Attempt 2 then passed the same serialized
  fence.

## Production checks passed

The successful deployment proved, in workflow order:

- both repository HMAC prerequisites were valid before host mutation;
- the request-idempotency key installed through immutable `set-once` custody;
- the request and agent-interchange host files were canonical, root-owned,
  group-readable only, and held distinct decoded key material;
- stale ambient cloud overrides were scrubbed before runtime-file sync;
- the immutable image started and the daemon became healthy;
- the four cloud workers were running and the exact seven-container surface
  (daemon, tunnel, four workers, and log collector) matched the release;
- the canonical public `/mcp` canary and exact-seven handle assertion passed;
- direct access remained gated by Cloudflare Access;
- the stop-writer state was restored and the terminal release-state receipt
  reported `outcome=deployed`, agreed active identity, and passed forward
  canary without rollback.

The immediately triggered uptime canary run `30777346026` also completed
successfully after the deployment.

## Remaining gate

The cloud fleet remains intentionally unable to claim the transactional
repository-to-spec queue until the supervised daemon's epoch-2 selector,
claim, heartbeat, terminal lifecycle, and single-active activation checks are
wired and independently reviewed. The ordinary private Branch must then be
created or remixed and activated through a rendered chatbot conversation.
Parent tasks 5.1 and 5.2 therefore remain open.
