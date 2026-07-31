## 1. Implementation

- [x] 1.1 Add a red regression proving pressure validation fetches origin and
  classifies `--status-ref origin/main`.
- [x] 1.2 Reuse the current-main snapshot helper for pressure-only validation.
- [x] 1.3 Add a red lifecycle regression for a graceful restart whose prior
  supervisor exits terminally.
- [x] 1.4 Preserve the explicit fresh-run decision through the launch block.

## 2. Verification And Release

- [x] 2.1 Run the focused supervisor/watchdog tests, Ruff, and strict OpenSpec.
- [ ] 2.2 Obtain independent exact-head review.
- [ ] 2.3 Merge, refresh the detached local controller, restart it, and prove a
  genuine exhausted result idles without a failure strike.
