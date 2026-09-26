# P1: Requested model selectors are not necessarily public identifiers

Open at `b655942b7579731962e75451a9618f99e04da000`, 2026-09-26 Windows review.
`tinyassets/storage/learned_models.py:83` accepts account-bearing Bedrock ARNs.
The actual success hook writes such a requested ID, including its account number,
to the cross-user catalog. Private deployment names also satisfy the regex.
Conversely, documented native selectors such as `sonnet[1m]` are rejected.

Evidence, official source and verification command:
[round-2 review](../reviews/2026-09-26-learned-catalog-round-2.md).
Separate public contribution eligibility from private execution selection;
success and syntax alone cannot establish that a selector is public.
