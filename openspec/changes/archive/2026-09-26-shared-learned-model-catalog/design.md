# SUPERSEDED — kept for the refutations, not as the design

The shipped design is in `proposal.md`: a typed id is personal forever, and sharing
is a reviewed file per source kind (`models/<source-kind>.json`) plus the ordinary PR
flow. Everything below describes the THIRD of three shapes that were built and
refuted — a platform-wide shared table with a distinct-owner promotion threshold.
It is kept because the refutations are the reason the shipped shape is the shape:

* a charset cannot tell a public model name from a private account-bearing selector;
* "used by two owners" does not imply public — colleagues share one org's private id;
* attestation plus peer confirmation worked and was over-built for the problem.

Do not implement anything below.

---

# Design

## The three fields, and why nothing else

```
learned_models(source_kind TEXT, model_id TEXT, first_verified_at TEXT,
               PRIMARY KEY(source_kind, model_id))
```

`source_kind` is the connection's existing `source_kind`, already present on every
row of the advisory options document. It is a KIND (`subscription_cli`,
`api_key_http`, …), not a connection id and not a provider account — two users on
the same kind of source are the ones who should share this evidence.

There is no `owner_user_id`, no `universe_id`, and no counter of how many users
verified an id. A counter sounds harmless and is not: "3 universes have verified
this id" is a population fact about users, and combined with timing it narrows who.
The primary key makes a second verification a no-op, so nothing accumulates.

`first_verified_at` is a property of the ID, not of a person: the first time this
platform saw the id work at all. It exists only to break a version-tuple tie.

## Where a row is written

At the one point where a call has already succeeded through a source and the
model id is known — the native terminal the coordinator commits on success. The
write is best-effort and never part of the turn's own transaction: failing to
learn must not fail a turn that worked. Nothing is written on a refusal, a
capacity hold, an unconfirmed transport outcome, or an owner declaration.

## Class and version, with no vendor knowledge

One function, `model_class_and_version(model_id)`, returning `(class, version)`.

The rule, applied to the id split on its own separators:

* A token that is entirely digits, or a dotted run of digits, is a **version**
  token.
* A token that is an 8-digit date stamp is a **version** token (dates sort as
  numbers and that is all this needs of them).
* Every other token — including a named suffix like `sol` or `astra` — is part of
  the **class**.
* The class is the remaining tokens joined in order. The version is the tuple of
  version tokens in order.
* An id with no version tokens is its own class with an empty version, which sorts
  below any explicit version. An id that cannot be split at all is its own class.

Consequences, which are the tests:

| id | class | version |
|---|---|---|
| `claude-opus-4-6` | `claude-opus` | `(4, 6)` |
| `claude-opus-4-7` | `claude-opus` | `(4, 7)` |
| `claude-fable-5-1` | `claude-fable` | `(5, 1)` |
| `gpt-5.6-sol` | `gpt-sol` | `(5, 6)` |
| `gpt-5.7-astra` | `gpt-astra` | `(5, 7)` |
| `claude-opus-4-6-20260115` | `claude-opus` | `(4, 6, 20260115)` |
| `some-model` | `some-model` | `()` |

`claude-opus-4-6` and `claude-opus-4-7` share a class, so only `4-7` is
contributed. `claude-fable-5-1` is its own class and is always contributed.
`gpt-5.6-sol` and `gpt-5.7-astra` are different classes, because a named suffix is
not a version — which is exactly the property that needs no vendor knowledge.

Version tuples of different lengths compare on their common prefix first, then the
longer tuple wins, so `4-6-20260115` is newer than `4-6`. Equal tuples fall back
to the earlier `first_verified_at`, so the id that has been known to work longest
wins a tie rather than an arbitrary one.

## What a user sees

For each source kind on the universe's connections:

1. Catalog rows for that kind, reduced to the newest of each class.
2. Union the universe's own ids — whatever it already had, declared or enumerated.
   A union, never a filter: an id the user already has is never removed because
   the catalog knows a newer sibling.

Catalog-contributed rows carry a distinct `availability_basis` so the app can be
honest about where the id came from: it is verified to have worked *somewhere* on
this kind of source, which is not the same as verified for *this* connection. They
are candidates, and serving still needs this universe's accepted model access.

The currently-saved model keeps its "current" tick even when the union does not
contain it and even when it is not usable — the dropdown bug fixed in #4027 —
which is a property the union must not break, so it is tested here too.

## Deliberately not in scope

- No per-provider code and no provider registry. The catalog is keyed on a kind.
- No pruning of ids that stop working. A row is evidence that an id worked once;
  deciding it no longer does is a per-connection judgement the availability path
  already makes, and a shared store must not act on one user's failure.
- No ranking or preference. The catalog contributes candidates; ordering stays
  where it is.
