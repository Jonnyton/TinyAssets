# Worktree purpose

Purpose: tier-lookup-fail-safe
Provider: claude-code
Branch: claude/tier-lookup-fail-safe
Base ref: origin/main
Issue/PR: fixes a crash path introduced by #2618 (effect quota, dark)
PLAN refs: metering
Ship condition: an unusable universe directory cannot stop an outbound effect
Abandon condition: n/a
Pickup hints: the bug is that the tier is resolved as an ARGUMENT, so it runs outside
  reserve_effect_quota's guard — the guard that makes metering harmless while dark
Memory refs: silent-failure-dispatch-and-tests
Related implications: none
Idea feed refs: (none)
