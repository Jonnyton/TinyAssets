# Background readiness budget regression contract

September19 2026 UTC, PR3876, supporting test correction only.

Required-tests run35423427142 found one new failure on59416a78:
`test_background_prelaunch_failures_do_not_spend_provider_budget[route]`.
Windows `python -m pytest -q tests/test_background_work_agent.py -k prelaunch
--tb=short --show-capture=no` reproduced one failed/one passed before correction.

The existing independently reviewed startup design explicitly moves route
readiness after provider admission, while retaining authority before admission.
That permits cold-start recovery; the existing finally path cancels an unused
reservation with zero token/cost settlement. The stale test expected no row for
route failure, conflicting with the reviewed foreground/background contract.

The amendment changes no runtime: require one cancelled-before-launch row for
route/discovery failure, zero provider/tool calls and zero tokens/cost; add an
authority-refusal case proving no reservation is created before authorization.
No quarantine, test exclusion or gate is modified.

Windows focused background/readiness/foreground cohort:61 passed, no skips,
46.65seconds. Ruff and diff checks passed. Linux and fresh exact-head independent
review remain release gates; prior59416a78 approval is not approval of a new head.
