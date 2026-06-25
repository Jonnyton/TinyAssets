# Tick — usage

A tiny mono provenance link. Use it to name where a value, claim, artifact, or
piece of evidence came from.

```tsx
import { Tick } from "@tiny/design-system";

<Tick href="#source" label="source" />
<Tick href="https://tinyassets.io" label="field note" external />
<Tick label="observed" />
```

Do: keep the label short and use Tick only for provenance/source context.
Don't: use it as a decorative badge, CTA, or status pill.
