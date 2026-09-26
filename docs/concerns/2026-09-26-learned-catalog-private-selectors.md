# P1: Requested model selectors are not necessarily public identifiers

Open at `b655942b7579731962e75451a9618f99e04da000`, 2026-09-26 Windows review.
`tinyassets/storage/learned_models.py:83` accepts account-bearing Bedrock ARNs.
The actual success hook writes such a requested ID, including its account number,
to the cross-user catalog. Private deployment names also satisfy the regex.
Conversely, documented native selectors such as `sonnet[1m]` are rejected.

## Evidence (inlined: a concern must be actionable from a clone)

Codex round 2 on PR #4028 drove the real success hook and it published this
synthetic selector verbatim to the cross-user table, AWS account number included:

    arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0

The same rule REJECTS documented native selectors `sonnet[1m]` and `opus[1m]`,
which loses their learned availability. Boundary probes that pass: `a::b`, `a//b`,
`a..b`, 128 alphanumerics. Fail: 129 characters, punctuation-only tails.

## Why no character rule closes this

The distinguishing property is not the character set -- it is whether the string
embeds an account or tenant identifier, which cannot be detected without exactly
the per-vendor knowledge this capability's own requirement forbids ("provider
agnostic ... no new patches for providers"). Two review rounds turned on this one
question, which is the signal that the shape is wrong rather than the regex.

Separate public contribution eligibility from private execution selection; success
and syntax alone cannot establish that a selector is public.

## Options put to the founder (2026-09-26)

1. Contribute only source-ENUMERATED ids -- public by construction, but empty for
   exactly the sources that cannot enumerate, which is the case the feature exists
   for.
2. Per-universe opt-in sharing -- the owner decides, which is the only party that
   can distinguish a public name from a private selector. Needs a consent surface.
3. Ship with the leak documented -- rejected: a shared store leaking an account id
   is what the cross-user floor exists to prevent.

Recommended: 2. Awaiting the founder's answer; PR #4028 is held draft until then.
