# Design

## The decision that shapes everything else: who identifies the service

Three options were available, and only one satisfies *"even ones we havent
thought of."*

| Option | Covers unknown services | Per-service code | Verdict |
|---|---|---|---|
| Preset table, extended | No | Yes, one row per service | Rejected — fails the stated requirement on its first use |
| Client-side prefix heuristics | Only what was enumerated | Yes | Rejected — same failure, dressed as inference |
| Model reads the shape | Yes | None | **Chosen** |

A lookup table is the hard-coded-effector shape `AGENTS.md` rules out, and it
fails precisely where the founder aimed this: the API nobody enumerated. A model
already knows what `api.stripe.com` is, what a `xoxb-` prefix means, and what
endpoint opens a pull request — including for services that postdate this code.
That is the only mechanism here that keeps working without maintenance.

## The tension: inference wants the credential, and must not have it

Identifying a service is easiest with the credential in hand, and that is exactly
what must not happen — a credential sent somewhere to be *identified* has been
disclosed, whatever the recipient does next.

The resolution is that **the identifying part of a credential is not the secret
part.** `github_pat_`, `sk-`, `xoxb-` are public, documented, low-entropy
prefixes. The entropy that makes a token a secret carries no information about
which service it belongs to. So the split is clean and lossless for this purpose:

```
paste:  github_pat_11ABCDE...93 chars total
sent:   {label: null, prefix: "github_pat_", length: 93}
kept:   everything after the prefix — never leaves the browser
```

Plus anything the user pasted that is *already* non-secret and highly
identifying: hostnames, URLs, a curl line, field labels like
`SLACK_SIGNING_SECRET`. Those are usually enough on their own.

The server-side operation refuses payloads that contain full credential values
rather than trusting callers to have done the split — the guarantee is enforced
at the boundary, not documented at it.

## The confirmation step: proposed, and cut

The first draft kept one click — the user reading a single sentence before the
deposit. The argument for it was that the endpoint allow-list is the only thing
bounding a leaked credential, and a human glance is cheap.

**The founder was shown that tradeoff and cut it (2026-08-27, "cut").** Pasting
is the whole interaction. This section records what that decision costs and what
carries the weight instead, because the decision is sound only if something does.

What the click was actually protecting against was never the *width* of the
grant — the validator bounds that either way, and a confirmed grant and an
unconfirmed one are equally narrow. It was protecting against the grant pointing
at the **wrong host**: a credential deposited against `api.evil.com` is usable
against `api.evil.com` on its first call. Confirmation was a human noticing that.

With the click gone, three things carry it:

1. **The paste is data, never instructions.** This moves from hygiene to
   load-bearing. Injected text in a pasted "credentials page" is the one input
   that could steer a host, and no human now reviews the result.
2. **An ungroundable host is a failure, not a guess.** If the resolver cannot
   tie a host to the credential's identity or the user's own intent line, it
   reports that it could not resolve. Depositing against a hallucinated host is
   the outcome to refuse, not to soften.
3. **The receipt makes it immediately visible and reversible.** The sentence
   still gets shown — after the fact, with change and remove attached. The
   founder's own standing ask from the same evening was that every world-facing
   action return a receipt; this is that, not the cut step wearing a hat.

The honest residue: a wrong inference now becomes a live connection for however
long it takes someone to read the receipt. That is the accepted cost, and it is
bounded — the grant is still one method on one path, and the credential still
only ever reaches the vault.

## Why the manual fields stay

A model that reads a paste wrongly must not produce a dead end. The explicit
fields move behind a disclosure, pre-filled with whatever was inferred, so a
wrong guess is a correction rather than a restart. This is also the migration
path: the existing form keeps working throughout, and the paste box is a faster
front door onto the same deposit.

## What is deliberately not touched

`connect_http`, `_parse_allowed_endpoints`, and the per-endpoint method gate are
unchanged. A confirmed proposal is validated by the identical code path as a
hand-authored deposit, so inference cannot express a grant a human could not.
That keeps this change out of the egress-security blast radius: the worst a bad
proposal does is get refused, or get confirmed as a narrow grant to the wrong
path — recoverable, and visible in the sentence the user confirmed.

## Open question for the founder

Whether the intent line ("what do you want it to do?") is required or optional.
Optional is assumed here, because a paste containing a hostname or a labelled key
is usually self-identifying and asking is the thing being removed. If inference
proves weak without it, promoting it to required is a one-line change and no
spec change.
