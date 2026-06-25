# Term — usage

Inline first-use definition for a project phrase. The text gets a dotted
underline and shows the plain-words definition on hover or keyboard focus.

```tsx
import { Term } from "@tiny/design-system";

<p>
  The fix must preserve <Term def="User-visible operation without a host process online.">zero-host uptime</Term>.
</p>
```

Do: use it once where a term first appears. Don't: underline repeated mentions
or use it for decorative emphasis.
