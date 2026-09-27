# Two authenticated accounts do not make a model selector public

**Filed / Verified:** 2026-09-26, Windows, Python 3.14.
**Severity:** P1, must fix before merge.
**Head:** `bfb1692500737e043cdae54e5d69f51f6b22a2f6`.

## Source: final round-3 review finding

The threshold counts platform account subjects, not people or independent
ownership of the model service. `tinyassets/auth/workos_provider.py:217,237`
maps the JWT subject directly to `Identity.user_id`;
`tinyassets/universe_server.py:3933` passes that ID to the request capability;
`tinyassets/provider_assignment.py:1337` returns it to the turn adapter;
`tinyassets/agent_turn_coordinator.py:215` records it. Reconnecting, changing a
binding, or changing universes under the SAME subject does not manufacture another
owner. No person-uniqueness check or upstream-account uniqueness constraint sits
on this path.

`tinyassets/storage/learned_models.py:214-222` publishes any identical selector at
two subjects. One person with two accounts satisfies that condition. Even perfect
person deduplication would not fix the premise: two people may legitimately use
the same private deployment/account selector. Source kind plus equal text does
not establish that a name is public or even names the same service.

A targeted `python -` probe invoked the real
`AgentTurnCoordinator._learn_verified_model` with two synthetic account subjects,
the same requested ARN, and separate universe directories. `for_source_kind`
returned the ARN verbatim, including `123456789012`. This exercises the success
hook, not real authentication or a live provider call. The account identity
boundary above is established by source inspection.

Publication eligibility needs evidence of permission to publish independently of
popularity. A larger threshold or stronger character rule does not establish
that permission. Preserving published rows after account deletion also preserves
private selectors admitted by this flaw.

The round-3 spec assertion that an account-bearing selector cannot be reached by
a second owner is contradicted by this model. Proposal/design still describe the
earlier single-verification shape and need reconciliation with the final design.
Round 3 is final; this finding does not request another review round.

Verification command (only the permitted suite):
`python -m pytest -q tests/test_learned_model_catalog.py tests/test_learned_catalog_grant_boundary.py tests/test_model_class_derivation.py`
reported **94 passed**. Repeated-owner fixtures do not establish the required
person or upstream-account uniqueness property.


## What the author fixed and did not (2026-09-26, end of the three-round cap)

Fixed from the same round: an owner's own verified id now actually reaches their own
list (`_own_verified_candidates`), and the reset classification says what it does
instead of promising a blocker it never had.

NOT fixed, because it is not an implementation defect. The threshold is a founder
DECISION (2026-09-26, chosen over per-universe opt-in sharing), and this finding says
the decision does not achieve its goal. The strongest form of it is not about account
uniqueness at all:

> two genuinely different people can use the same private deployment selector

Two colleagues on one company's Bedbrock deployment, or two contractors given the
same org ARN, are two real people with two real accounts, and the id they share is
still private to that organisation. Deduplicating PEOPLE would not help; "used by
more than one owner" simply does not imply "public". Popularity is not a
sharing permission.

So no threshold value fixes this, and neither does a charset (rounds 1-2 established
that). What closes it is an explicit sharing boundary -- the owner saying "publish
models that work here", which is the per-universe opt-in that was option 2 when the
founder chose option 3.

Held for the founder. PR #4028 stays draft; three review rounds are spent and a
fourth is not authorised.
