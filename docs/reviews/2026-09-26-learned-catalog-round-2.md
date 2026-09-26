# Learned catalog round 2

Reviewed head: `b655942b7579731962e75451a9618f99e04da000`, against `03a6828c`.
Reviewer: Codex, directly; no delegated agents, worktrees, or provider subprocesses.
Date/environment: 2026-09-26, Windows, Python 3.14.

Verdict: **block**. The legacy admission leak and shared-value privacy floor remain.
This is round 2, not a request for round 3. Apply the repository's primitive rule:
centralize the distinction between visible candidates and admitted models, and
distinguish a public catalog identifier from a private invocation selector.
Successful invocation plus an identifier regex is not evidence of publicness.

## 1. Admission: DISAGREE_EVIDENCE, P0 residual

`tinyassets/api/model_options.py:183` calls `_native_models`, including learned
rows. For a live legacy native binding with absent/automatic preferences, line 198
copies that entire connection into `plan.catalog`. No contributed-row exclusion
or `model_access_optin_required` reason is added on this path.

Direct local reproduction used `_served_context` fixture setup (no test execution
outside the three permitted files), a synthetic codex executor, a temporary DB
outside the repo, and real `_collect(base, 'owner-1', 'u-owner')`. After recording
`vendor-newline-9-1`, the returned document contained:

```json
{"choice_authority":"legacy_single_provider","accepted_model_access":{},
 "learned_row":{"in_candidate_catalog":true,"reasons":[],"order_index":null},
 "order":[{"provider_ref":"codex","model_id":""}]}
```

This reproduces false selectable admission, not an execution-authority bypass.
Automatic order remains the default. `save_model_preferences` deliberately accepts
advisory references (`tinyassets/api/model_preferences.py:18`), so a contributed ID
can be saved, but the corrected manifest planner excludes it from order:
`served_model_plan.py:407`, `model_policy.py:349` and `:391`. A saved explicit choice
on a legacy assignment requires a manifest; it cannot exploit the automatic-only
legacy catalog branch to gain execution authority.

## 3. Identifier/privacy: DISAGREE_EVIDENCE, P1 residual

`tinyassets/storage/learned_models.py:83` accepts this invocation selector
(the account number is synthetic):

`arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0`

Invoking the actual `AgentTurnCoordinator._learn_verified_model` with that requested
ID writes it verbatim, account number included, to the shared `subscription` rows.
The same applies to private deployment names such as `owner-alice-private-9`.
The owner choosing a private selector does not make it public data.
[Claude's model configuration](https://code.claude.com/docs/en/model-config)
explicitly permits inference-profile ARNs and deployment names as model settings.
This is the same round-1 shared-value privacy finding, not a demand for a tighter
punctuation blacklist.

The rule also rejects documented native selectors `sonnet[1m]` and `opus[1m]`.
That is a learning/discovery availability regression, not an inability to execute
an already granted selector. The same official documentation lists those aliases.
`a::b`, `a//b`, `a..b`, and 128 alphanumeric characters are accepted; 129 characters
and a first alphanumeric followed only by punctuation are rejected. Acceptance of
punctuation alone is not an injection exploit: SQL uses bound parameters and the
native execution path uses an argument vector.

## 4. Latency/failure honesty: DISAGREE_CONCERN, nonblocking

The 30-second setting is gone (`learned_models.py:109`, `:115`, `:123`). Failure
returns False and logs; losing an optional learning attempt is acceptable and
does not erase existing rows. A subsequent successful call can retry.

However this is a SQLite busy timeout, not a measured end-to-end guarantee.
Direct `BEGIN EXCLUSIVE` probes on this Windows/Python 3.14 host measured
`_catalog_candidates` at 0.779 seconds and `record_verified_model` at 0.807 seconds.
Both logged OperationalError. The read returned `()`, the write False, and after
unlock the original row remained. Do not extrapolate these timings to Linux.
The new test only asserts less than 3 seconds.

The narrowed/logged catch at `served_model_plan.py:226` closes the bare-exception
finding locally. The client still receives an empty contribution without a
catalog-unavailable diagnostic; the warning is operator-visible only. Track this
as advisory degradation/latency work, not another pre-release floor gate.

## 5. Class/tie: DISAGREE_EVIDENCE, P2 residual (nonblocking)

The exact `some_model`/`some-model` bug and timestamp tie are fixed. All 120 input
permutations of five representative rows returned the same ordered IDs.

But `model_class.py:77` preserves only the separator immediately before the next
surviving token. `vendor/2-model` and `vendor-2-model` both become `vendor-model`,
so the namespace distinction can still be lost and one ID discarded. Conversely,
`vendor/model` has a different class from `vendor/2-model`. This is a concrete
remaining limitation of the separator-preservation claim. Track it without
expanding the floor review.

## 2. Source-controlled response: AGREE

`agent_turn_coordinator.py:198` reads the requested selection; response.model and
reported_model cannot inject into this writer. Empty selections write nothing.
Capacity replacement at `:553` comes from `_next_candidate` (`:70`), whose plan or
work-adapter candidate set is retained and authorized, not supplied by the error.
Native automatic order uses the empty default; explicit native choices/fallbacks
must already be authorized. Publishing the successful fallback's requested ID is
correct. This closes response substitution, but does not establish publicness
of that ID (finding 3).

## 6. Empty admitted set: AGREE

No new regression found for a valid native grant. `served_model_plan.py:168`
starts with explicit granted IDs (required nonempty by `ModelAccess`) or the
empty default for other scopes. Own IDs precede learned union/dedup and retain
their owner-declared basis. Thus an ID both learned and granted survives filtering.
A learned-only ID was never valid execution authority. Advisory `allow_empty=True`
still works; execution with no eligible candidate correctly refuses at `:478`.

## Verification

Command: `python -m pytest -q tests/test_learned_catalog_grant_boundary.py tests/test_learned_model_catalog.py tests/test_model_class_derivation.py`

Result: **85 passed in 2.74s**, at the head above. No full suite or live production
execution. Additional direct Python probes covered legacy collection, identifier
validation and writer storage, class permutations, and exclusive-lock behavior.
`git diff --check 03a6828c..HEAD` passed. The grant test at
`tests/test_learned_catalog_grant_boundary.py:91` checks a document after granting;
despite its name/docstring, it does not execute a native turn.
