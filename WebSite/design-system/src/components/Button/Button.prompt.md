# Button — usage

The single action control. `variant="primary"` is **ember** and reserved for the
one most important action on a surface; step down to `secondary` (violet),
`ghost` (quiet outline), or `link` (inline) for everything else. Provide `href`
to render an anchor (navigation); omit it for a real button (`onClick`).

```tsx
import { Button } from "@tiny/design-system";

// Primary CTA (one per surface)
<Button href="/start">Connect a chatbot</Button>

// Secondary / supporting
<Button variant="secondary" href="/soul">Fork the pattern</Button>

// Quiet / inline
<Button variant="ghost" onClick={openLoop}>Read the loop</Button>
<Button variant="link" href="/legal#token-disclosures">Disclosures →</Button>
```

Do: keep one ember primary per view. Don't: use `primary` for low-stakes
actions, or `link` for the main CTA.
