## Context

The uptime-canary workflow is triggered by schedules, manual dispatches, and every completed `Deploy prod` workflow. A failed deploy skips the probe job, leaving the alarm sink with empty output. Because the current sink treats every non-red value as green, it can mutate issue state and close a live `p0-outage` incident without a successful current probe. The sink must continue to use a failing red canary run as threshold evidence for the next red, so unknown observations cannot fail the workflow.

## Goals / Non-Goals

**Goals:**

- Model the sink input as literal `green`, literal `red`, or unknown.
- Stop unknown inputs before any label lookup/creation, issue lookup, issue mutation, or paging eligibility change.
- Preserve red threshold, issue append/open, and page-eligibility behavior.
- Require literal `green` for recovery comment and closure.

**Non-Goals:**

- Changing the probe's red/green composition, trigger set, threshold, paging policy, or deploy behavior.
- Treating a skipped probe as red or manufacturing a recovery from a prior run.

## Decisions

### Guard unknown before GitHub mutations

The github-script step initializes no-page outputs, then returns when `OVERALL` is neither `red` nor `green`. This guard precedes label and issue API calls. It records an Actions warning and step summary describing the unrecognized value, but exits successfully.

An early guard is preferred to a late `else` branch because label creation is itself an issue mutation and must not run for unknown state.

### Keep threshold evidence strictly red

Only the literal red branch calls `previousRunWasRed`, opens or comments on an incident, and enables paging. The unknown guard succeeds so a skipped probe does not become a failed canary run that a future red would mistake for threshold evidence.

### Make recovery branch literal

The recovery comment/close code is placed under `if (overall === 'green')`. This prevents future non-red values from silently acquiring recovery semantics.

## Risks / Trade-offs

- [An outage might remain open after an unknown deploy-triggered run] → This is safer than fabricated recovery; the next verified green closes it.
- [Unknown results need operator visibility] → Emit both a warning and workflow summary without changing issue state or run conclusion.
- [Text-based workflow tests can miss GitHub runtime semantics] → Pin branch ordering, literal comparisons, no-op summary, and red/paging invariants in focused tests; actionlint validates syntax.
