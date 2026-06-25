# Ladder — usage

Outcome ladder for proof states. Rungs are unlit by default. A rung only lights
when it has both `lit: true` and an `evidence_url` that proves the outcome.

```tsx
import { Ladder } from "@tiny/design-system";

<Ladder
  start="outcome"
  rungs={[
    { name: "Local build", lit: true, evidence_url: "#build" },
    { name: "Rendered proof" },
    { name: "Live user path" },
  ]}
/>
```

Do: keep unproven outcomes unlit. Don't: mark progress as lit without evidence,
or use the ladder as a decorative timeline.
