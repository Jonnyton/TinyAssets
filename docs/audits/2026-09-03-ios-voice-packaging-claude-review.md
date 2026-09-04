All seven changed files have been inspected against the four intent points.

---

AGREE — `mobile/scripts/add_ios_scheme.py` installs `NSMicrophoneUsageDescription` with the exact purpose copy, fails closed (returns 1, writes nothing) when an existing description doesn't match, and is idempotent when the key/value already match (`install_configuration`, lines 48–88).

AGREE — Both `ios-build.yml` and `ios-release.yml` add a `grep -q "<key>NSMicrophoneUsageDescription</key>"` check with correct indentation immediately after the existing URL-scheme grep, so an unsigned or signed build with a missing key fails the workflow.

AGREE — `tests/test_mobile_ios_release.py` covers idempotency (`test_ios_configuration_installer_adds_release_keys_idempotently`), fail-closed conflict rejection with the file left untouched (`test_ios_configuration_installer_rejects_conflicting_microphone_copy`), and presence of the grep guard in both workflows (`test_ios_workflows_verify_microphone_purpose_key`). The claimed "13 passed" in `mobile-launch-handoff.md` reconciles correctly (8 pre-existing tests in this file + 3 new + 2 from `test_onboarding_app.py` matched by `-k`).

AGREE — Docs consistently keep voice dark: `app-store-launch.md`'s checklist marks the microphone purpose staged (`[x]`) but leaves background/stop proof and privacy re-evaluation unchecked (`[ ]`); `host-actions.md` and `mobile-launch-handoff.md` both gate voice-enabled submission on physical-device proof and a provider-retention-based privacy re-evaluation, with no premature "release-ready" claim anywhere in the diff.

AGREE — The microphone purpose string is byte-identical between `add_ios_scheme.py:39-42` and its quoted form in `docs/ops/app-store-launch.md:130-132`, so the docs and the enforced runtime string can't drift apart silently.

DISAGREE_CONCERN: `.github/workflows/ios-build.yml:56` and `.github/workflows/ios-release.yml` step name ("Register the tinyassets:// URL scheme (in-app OAuth return)") no longer describes what the step does now that it also stages the microphone purpose key — purely cosmetic, not a functional or release risk.

VERDICT: APPROVE

## Author disposition

Accepted the non-blocking naming concern for `ios-build.yml`; its step label now
describes both installed keys. The release workflow already used the broader
"Install native configuration and artwork" label, so it needed no change. No
runtime or release behavior changed after the approving review.
