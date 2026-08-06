
## Addendum: the true root cause, reached at last

`current: 2026-08-06 00:40Z`. Everything above is real but downstream. The
actual reason the drain cannot be productive is one line from `converse`:

```
status: held / setup_required
missing: ["compute", "model_access"]
"Engine assignment is not exposed by the advertised handles."
```

**The universe has no engine.** It was never assigned compute of its own, and
no advertised handle can assign one.

The automation's provider binding is real but is not the universe's engine:

```
binding_id  pwb_fbddd0e8b76b837a266488a23403f0b3
provider    claude-code
max_invocations 64      max_cost_microunits 64
```

Those budgets are tiny, and every soul-loop slice now fails with
`Pinned writer provider 'claude-code' exhausted` after ~10-26s of real work.
Rebinding to the owner's other subscription is refused:

```
provider_binding_setup_required
"requester-owned provider enrollment is unavailable"
```

Only `claude-code` is enrolled, and the enrollment manifest
(`TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON`) is a server-only deploy
secret — deliberately not writable from chat.

So a founder holding two paid subscriptions cannot point their universe at
either one through the product. This is exactly the gap
`openspec/changes/user-assigned-llm-policy` was written for on 2026-08-05,
quoting the host directive verbatim; that change is 3 of 31 tasks done.

### Why the earlier layers still mattered

Each was genuinely blocking and had to be cleared before this one became
visible at all:

1. admission hashes typed by provenance (#2322) -- 3 of 4 rows were invalid
   on arrival;
2. `/data/.active_universe` absent -- workers served the wrong universe;
3. the universe's loop pointed at "E2E Walk Test Branch v2", which fails in
   <1s on a missing `topic` input regardless of executor;
4. `TINYASSETS_SOUL_LOOP_DISPATCH=on` routing to an unshipped `workflow`
   module -- crash-loop, no capacity.

With all four cleared, the pipeline runs end to end: claim -> spawn -> correct
branch -> LLM dispatch. It reaches the engine and finds none.

### What would make it 24/7

Either enroll a second provider in the manifest and rebind, or ship the
owner-facing engine assignment that `user-assigned-llm-policy` specifies. No
amount of worker, fence, or queue work substitutes.
