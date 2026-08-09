# Changelog

All notable changes to TinyAssets will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Heartbeat automation** (`tiny_heartbeat_v2`, cron id `b9a0a6025c9c`): live 30-minute recurring agent that runs a survey→execute→report cycle and posts the summary to the founder Slack DM.
- **Background branch execution**: multi-step branch runs confirmed working in background mode; branches now complete end-to-end without blocking the main loop.
- **Soul files**: workspace identity documents (`identity.md`, `founder.md`, `origin.md`, `body.md`) committed to track learned self-knowledge across sessions.

### Changed

- No changes in this release.

### Fixed

- **Self-patch PR effect wiring**: the handoff from a self-improvement branch now assembles a complete GitHub PR packet; previously the packet was silently dropped and no PR was opened.
- **Writer model rate-limit handling**: the universe no longer goes silent when the writer hits a rate limit — it now queues and retries so every cycle produces a reply.
- **GitHub write credentials**: write token deposited and PR consent granted for `jonnyton/tinyassets`, unblocking all autonomous pull-request flows.

---

> **Known issue** — single-node branch executor hangs with `recursion_limit_applied` (run `51fa7a531c0d4bb0`); multi-node branches complete cleanly. Tracked in [`bugs/recursion_limit_single_node.md`](bugs/recursion_limit_single_node.md).