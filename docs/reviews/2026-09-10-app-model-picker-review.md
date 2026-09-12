# App model picker independent review

September10 2026. Exact f9652d00 vs e8d69c3b, Claude11747 exit0 after420s:
**ADAPT**, one required correction. The reviewer reproduced20picker tests4.84s
on Windows. Full substantive final output: output/app-model-picker-review.md.

Required: without any loaded snapshot, render() incorrectly said "Saved default:
Automatic". Correct it to Not loaded; retain Automatic when a successful snapshot
contains policy=null. Reviewer explicitly said this one-line correction does not
need another review round. Applied with failed-first-read and valid-empty-policy
regression cases; verification recorded with the correction commit.

Correction verification on September10, Windows Python3.14:

```text
python -m pytest -q tests/test_app_model_picker.py tests/test_app_model_choice.py tests/test_onboarding_model_preferences.py tests/test_onboarding_app.py tests/test_brand_parity.py tests/test_mirror_parity_gate.py --tb=short --show-capture=no -rs
208 passed,1warning in31.51s
```

Actual Docker Linux, same six files and flags:208passed26.33s, zero skips.
419plugin mirrors/import, app checksum regeneration, Ruff and diff checks pass.

AGREE: actual/next/saved separation; opaque refs/inert rendering; fresh eligibility;
explicit empty fallback and order; typed/voice/queued/retried choice capture; CAS
and exact-home fence; epoch guards; stale display; native modal/keyboard/focus;
no access or spending authority created by selection.

Non-gating: definitive save errors could use more precise wording; absolute server
expiry depends on device clock; use-button null-safety relies on short-circuiting;
opening during save skips refresh; rebuilding select options may flicker with
arrow keys. Native explicit discovery, access-confirmation UI, non-home controls,
persisted receipts and current-attempt telemetry were acknowledged incomplete,
not counted as defects in this consumer slice. No live/deployment approval claimed.
