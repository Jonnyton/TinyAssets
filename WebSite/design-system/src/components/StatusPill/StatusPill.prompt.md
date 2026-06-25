# StatusPill — usage

A small mono capsule for daemon state. The dot colour follows the liveness
rule: **green only for genuine liveness**, amber for asleep/idle, ember for
error. Set `pulse` only when the state is truly live (it animates the dot).

```tsx
import { StatusPill } from "@tiny/design-system";

<StatusPill kind="live" pulse>live</StatusPill>   {/* real-time */}
<StatusPill kind="idle">asleep</StatusPill>       {/* normal, not an error */}
<StatusPill kind="paid" pulse>paid</StatusPill>
<StatusPill kind="self">self-host</StatusPill>
<StatusPill kind="error">error</StatusPill>
```

Don't make green decorative, and don't `pulse` a state that isn't live.
