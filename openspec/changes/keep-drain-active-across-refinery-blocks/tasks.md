## 1. Regression and implementation

- [x] 1.1 Change the focused alternative-candidate test to prove a distinct
  refinery hint remains immediately dispatchable after another refinery target
  is quarantined, and retain a same-target negative case; observe RED.
- [x] 1.2 Extend the alternative predicate to include `REFINERY` without
  weakening recent-block, consumed-target, or exact-target filtering; observe
  GREEN across the focused supervisor suite.

## 2. Foldback and live proof

- [ ] 2.1 Run full controller/watchdog tests, lint/format, strict OpenSpec
  validation, and an independent exact-head review.
- [ ] 2.2 Sync the delta into the main development-coordination spec, archive
  this change, land through a reviewed PR, and restart the local watchdog on
  the merged controller.
- [ ] 2.3 Record runtime evidence that a verified blocked refinery target is
  quarantined and a distinct refinery worker dispatches without the configured
  idle interval.
