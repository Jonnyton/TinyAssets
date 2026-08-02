## Why

Desktop release runs `30764595380` and `30766508516` remained inside the unsigned Windows lifecycle step until GitHub cancelled the job after fifteen minutes, despite the current supervisor's 300-second total deadline and the job's ten-minute fallback. The cancelled runs retained no logs, so the as-built `desktop-release-lifecycle-ci` requirement is again false and agent-runtime delivery loses a trustworthy Windows gate.

## What Changes

- Add a Windows regression where the lifecycle parent exits while an escaped descendant retains inherited output handles; require the supervisor itself to return within its bounded margin.
- Restore the archived design's actual isolation boundary: lifecycle output goes to private capture files without supervisor-owned pipe-drain threads whose EOF depends on every descendant.
- Keep diagnostic replay byte-capped, cleanup bounded, and the GitHub job timeout as defense in depth.
- Record exact recurring-run evidence and independently verify the repaired Windows lifecycle before treating the gate as green.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `desktop-release-lifecycle-ci`: add the parent-exits/descendant-retains-handles scenario to the independent total-deadline contract.

## Impact

The change is limited to the unsigned Windows desktop lifecycle supervisor, its workflow invocation, focused tests, OpenSpec contract, and verification evidence. It changes no installer payload, signing or publication path, product runtime, provider authority, or customer data.
