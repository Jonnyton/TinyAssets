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

## Why the user still confirms

The obvious reading of "the platform just figures it out" is that nothing is
shown. That would be wrong here, for one reason: the endpoint allow-list is the
only thing bounding a leaked credential. A host-wide grant on `api.github.com`
turns one stolen token into access to every repository the token can reach; a
one-path grant does not.

So the boundary is *shown*, not *authored* — one sentence, no vocabulary:

> This key will be allowed to **POST** to
> `api.github.com/repos/jonnyton/tinyassets/pulls` — nothing else.

The user reads a consequence instead of filling in a policy. That is the smallest
thing they can be asked to do while the grant stays narrow, and it costs one
click rather than five fields.

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
