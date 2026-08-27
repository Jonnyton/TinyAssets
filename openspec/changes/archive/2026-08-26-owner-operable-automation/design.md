# Design — owner-operable automation

## The open decision: what "run it now" should be

A `run_once` verb on `target=automation` was drafted on 2026-08-05 and
**rejected the same day**, on the grounds that `run_graph` already runs a branch
on command — verified live, run `6104ef4bb76f49bf` executed the drain's Branch
end-to-end on the cloud fleet. Adding a second verb over it is pre-built
convenience, not a primitive.

That rejection stands, and it is the reason this change does not simply
re-propose the verb. Three candidate shapes, with the trade-off stated:

1. **Expose Trigger as a user primitive.** An owner creates a Trigger bound to a
   published Branch version, with a cadence, and can fire or cancel it. A
   scheduled automation then *composes* from Branch + Trigger, and "run it now"
   is just firing your own Trigger. Most primitive, most work, and it makes the
   `automation` lane one shareable design among many rather than the only road.
2. **Owner-fired slice on the existing lane.** A control that emits one due
   Trigger for the owner's automation through the normal slice accounting, so
   the run consumes budget and produces a terminal receipt like any other slice.
   Smaller, but keeps the opinionated lane primary.
3. **Documented `run_graph` route only.** No new surface: make the connector
   resolve "run my automation now" to the automation's pinned
   `branch_version_id` and run that. Cheapest, but the run stays outside slice
   accounting — it produces no receipt, so health still shows an automation that
   has never progressed.

Recommendation: **(1)**, with (3) as the interim answer the surface should give
today. (1) is the only option that also satisfies the broader steer — users
composing their own scheduled work from reduced powerful primitives instead of
adopting our whole lane.

Whichever is chosen, the accounting question must be answered explicitly: does
an owner-fired run consume the provider binding's invocations and the
destination grant's action cap, and does it produce a terminal receipt? A run
that bypasses accounting is an authority hole; a run that produces no receipt
leaves health lying about progress.

## Why `next_action` needs a test, not care

`next_action` shipped naming `run_once` while no such operation existed, because
the label was written when the verb was still planned and outlived it. Live, an
assistant read that label and told the owner a job had been queued and a worker
had not yet claimed it. None of that had happened.

So the requirement is not "keep the label accurate" — it is that the set of
values `next_action` can emit must be **derived from or checked against** the
operations the handler accepts, with a test that fails when they diverge. Prose
discipline already failed once here.

## Why `resume` returning success is the same class of bug

`resume` sets `desired_state`. When `desired_state` is already `active`, it
writes nothing and returns success. An owner watching a dead automation pressed
it, was told it worked, and nothing changed — verified live. A control that
cannot affect the observed state should say so in its typed result rather than
report success. Same failure mode as the label: the surface asserting something
untrue about itself.

## Constraints carried from the existing lane

- Principal derives from authenticated request context; caller-supplied actor
  fields grant nothing.
- Writes stay revision-fenced.
- Nothing here widens provider or destination authority. The destination grant's
  `unprompted_action_cap` is separately known to be validated but never consumed
  (2026-08-05 probe: three consecutive evaluations all admitted), which is a real
  defect but belongs to its own change — noted here so this one is not read as
  fixing it.
- Stop-fencing for *future* slices is already sound and must stay that way. The
  known in-flight gap — a publish executing after a stop, because publish runs
  without a second activation CAS — is likewise out of scope here and needs its
  own lane.
