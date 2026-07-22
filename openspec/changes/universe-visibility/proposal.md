# Universe visibility model

## Why

There is no defined public/private model for a universe. Nothing expresses per-universe visibility
intent, so everything defaults to visible — and neither the platform nor a reader can tell whether
that is correct.

Found by live ui-test on 2026-07-21 (first-contact flow, Claude.ai incognito, connector added from
scratch, never authenticated). An anonymous caller enumerated every universe with metadata — name,
word count, activity dates, state — and read the `default-universe` commons, which currently holds
the project's own engineering backlog (patch requests, bug reports, identity/lease defect notes).

**This is a specification gap, not (only) a bug.** The existing universes are old and
publicly-intended; they carry no marking that would make them read as anything else. There was no
declared boundary to breach. That is exactly the problem: correctness is currently unstatable, so no
implementation can be verified against it. The model has to be defined before anything can be called
a leak or a fix.

Related but distinct: an unauthenticated session also resolves to a concrete account principal and
reports host daemon liveness, provider auth state, and host disk telemetry. That is an identity-
resolution defect handled in the `distributed-execution` change — no visibility setting would make it
correct, because none of it is universe content.

## What Changes

- **Define visibility levels** for a universe and state, for each, exactly what an unauthenticated
  reader may do: discover existence, read metadata, read content — as three separately-grantable
  capabilities rather than one flag.
- **Treat existence as privileged.** Listing a universe's name, size, and activity dates is
  disclosure even when its content is withheld. The ui-test demonstrated enumeration alone is
  informative.
- **Define the granularity.** Visibility applies per universe and per page: the observed commons
  mixed internal engineering notes with an unrelated public note in a single scope, so a
  universe-level flag alone cannot express intent.
- **Define the default** for a newly created universe, and the disposition of legacy universes —
  backfilled to an explicit level, or grandfathered with a recorded reason. No universe may sit in an
  undeclared state.
- **Make the declared level enforced and observable**, so a reader can tell what they are looking at
  and the platform can reject a read that the level does not permit.

## Impact

- New spec: `universe-visibility`.
- Affected: the wiki/commons read path, universe listing/enumeration, and per-universe config.
- Interacts with `identity-auth-and-access-control` (who the reader is) and `data-commons` (what the
  commons is for). Visibility answers "what may this reader see"; identity answers "who is this
  reader" — both are required and neither substitutes for the other.
