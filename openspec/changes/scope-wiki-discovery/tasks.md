## 1. Review Gates

- [x] 1.1 Obtain the Opus 5 current-main ADAPT verdict and fold its six required corrections into the planning artifacts.
- [x] 1.2 Classify and close #1478, #1491, #1477, #1471, and #1464 as stale/source-only with current-owner handoffs.
- [x] 1.3 Resolve the exact-artifact Opus 5 and independent Codex ADAPT findings and obtain exact-artifact approval before runtime edits or push.
- [x] 1.4 Fast-forward onto current `origin/main`, rerun claim/context gates, and confirm the exact write-set remains collision-free.

## 2. RED Tests

- [ ] 2.1 Rewrite the three existing positive search/since/ambient tests with explicit discovery or coordination intent and paired exclusion assertions; do not delete, relax, or xfail them.
- [ ] 2.2 Add failing default search/since/discovery-ambient tests that each assert a non-empty discovery result alongside coordination exclusion.
- [ ] 2.3 Add failing explicit discovery/coordination/all/invalid/empty/whitespace-only-scope tests with applied-scope and non-noisy scope-note evidence.
- [ ] 2.4 Add failing audience tests for overrides, blank/unset fallback, trimmed case-insensitive values, untagged fallback categories including `feature-requests`, custom/category-less discovery, invalid-audience coordination fallback, invalid-source coordination ambient scope, and no warning-log amplification.
- [ ] 2.5 Add failing category tests for search/since/ambient across pages and drafts, custom and absent categories, exact-read nested empty-normalized rejection with unchanged body, and filtering after audience.
- [ ] 2.6 Add failing structural tests for exact coordination/discovery reads, source-derived ambient scope, unchanged list behavior, and applied-scope evidence only on search/since/exact-read ambient responses.
- [ ] 2.7 Add parameterized failing visibility tests proving restricted search, since, and ambient candidates expose no path/title/excerpt/body under discovery, coordination, or all, with granted-reader positive controls.
- [ ] 2.8 Add a failing public-wrapper coupling test invoking `tinyassets.universe_server.read_page`: omitted public scope inherits discovery results while the public function/schema advertises no `scope` parameter.
- [ ] 2.9 Add a named failing 256-call dispatcher-level concurrency proof with non-empty byte-identical reference results, bounded response evidence, and no ContextVar/root-vacuity.
- [ ] 2.10 Capture the expected current-main RED evidence before implementation.

## 3. Core Implementation

- [ ] 3.1 Add pure request-local scope, source-audience, candidate-audience, and open-taxonomy category helpers in canonical `tinyassets/api/wiki.py`.
- [ ] 3.2 Thread `universe_id` into ambient retrieval and apply visibility before audience/category and before scoring or response construction on every retrieval surface.
- [ ] 3.3 Forward core `scope`, return applied scope plus a non-fatal default-filter note, and preserve exact body reads and list behavior.
- [ ] 3.4 Run `python packaging/claude-plugin/build_plugin.py`, prove canonical/plugin `api/wiki.py` byte parity, and reject any unintended generated diff.

## 4. Verification

- [ ] 4.1 Pass `pytest tests/test_api_wiki.py tests/test_wiki_tools.py -q`.
- [ ] 4.2 Pass the surrounding wiki and universe-visibility suites, Ruff on changed Python files, compile/import checks, and `git diff --check`.
- [ ] 4.3 Pass the named 256-call single-process request-local determinism proof and document its environment/date without claiming the separate §14 Track J load suite.
- [ ] 4.4 Pass `openspec validate scope-wiki-discovery --strict` and `openspec validate --all --strict`.
- [ ] 4.5 Obtain independent exact-head correctness/security/diff review and resolve every required finding.

## 5. Foldback and Public Proof

- [ ] 5.1 Sync the accepted delta into canonical `openspec/specs/wiki-commons/spec.md` and archive the change in the same landing lane.
- [ ] 5.2 Publish the reviewed PR and land it through required GitHub checks.
- [ ] 5.3 Prove the deployed source SHA and exact-seven `https://tinyassets.io/mcp` surface.
- [ ] 5.4 Rerun the dated changed-since and four onboarding-query contamination probes against live and record the before/after result mix.
- [ ] 5.5 Record a rendered chatbot onboarding conversation through the installed TinyAssets connector where default `read_page` returns useful commons material and excludes coordination history; defer build-success acceptance to the branch-authoring lane.
- [ ] 5.6 Inspect post-fix organic use and over-filtering; if none is visible, leave a dated monitoring row rather than claiming clean-user proof.
