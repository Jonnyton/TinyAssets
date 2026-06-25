# RitualLabel — usage

The small-caps mono kicker that sits above a heading or labels metadata. Same
look as the global `.eyebrow` class; use the component in React contexts.

```tsx
import { RitualLabel } from "@tiny/design-system";

<RitualLabel>Field note · 001</RitualLabel>
<h2>How the loop patches itself</h2>

// colour-coded label
<RitualLabel color="var(--ember-700)">Live evidence</RitualLabel>
```

Keep it to a few words; it's a label, not prose.
