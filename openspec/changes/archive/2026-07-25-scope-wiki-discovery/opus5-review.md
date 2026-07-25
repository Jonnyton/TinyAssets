# Opus 5 current-main review

Date: 2026-07-24 America/Los_Angeles
Reviewer: Claude Opus 5, high effort, isolated read-only CLI
Verdict: **ADAPT**

## Accepted direction

- `scope-wiki-discovery` is the correct current-main successor to stale #1550.
- Audience is relevance, not privacy or authorization.
- One existing wiki store and handler remain; no new tool, action, index,
  taxonomy whitelist, migration, or page move.
- Handler-level defaults are independently useful before the public
  `read_page.scope` parameter is advertised.
- The phase changes public `read_page` behavior immediately while leaving the
  exact-seven schema unchanged.

## Required corrections

1. Fix the pre-existing ambient-feed visibility defect in this phase.
   `_ambient_relevance_feed` currently lacks `page_visible_in_listing` and does
   not receive `universe_id`, allowing restricted page path/title/body excerpts
   to appear in recommendations.
2. For exact reads, omitted ambient scope follows the source page's audience.
   Search and since still default to discovery. This preserves
   coordination-to-coordination cross-referencing before a public scope
   parameter exists.
3. Rewrite the three existing positive search/since/ambient tests with explicit
   discovery or coordination intent and retain positive-result assertions.
4. Add `feature-requests` to coordination fallback because it is the fourth
   typed-filing category.
5. Missing audience uses category fallback; a present unsupported audience
   fails toward coordination. Custom and category-less pages default discovery.
6. Normalize category with the existing open-taxonomy slug rule. A non-empty
   value that normalizes empty errors with no results; valid unknown/custom
   categories return zero/matches and never become a whitelist.

## Required filter order

Universe ACL gate → `page_visible_in_listing` → audience → category →
scoring/ranking/truncation.

Visibility-first is structural: `scope=all` can never bypass authority and
restricted bodies never reach scoring. Audience result-count differences are
not privacy leaks because the root commons and coordination records are
public-by-definition.

## Compatibility correction

In-node wiki aliases may currently depend on mixed search/since defaults.
Every scoped response must include applied `scope`; when omitted scope filters
otherwise-visible candidates, return a non-fatal `scope_note` explaining
explicit in-process `coordination|all`. Do not add a compatibility shim.

## OpenSpec correction

- MODIFIED `Seed taxonomy is a set of defaults, not a closed whitelist` with
  read-side category normalization/filtering.
- ADDED one `Default discovery scope separates commons knowledge from
  coordination history` requirement.
- Do not create separate category/audience requirements that duplicate each
  other.
- Treat ambient visibility as a defect against existing universe-visibility
  truth, not a second visibility requirement.

## Collision disposition

PRs #1464, #1471, #1477, #1478, and #1491 carried one stale inherited
patch-loop wiki diff in a disjoint trigger-receipt region. They did not own
search/since/read/ambient/category behavior. All five were closed source-only
with current distributed-execution/patch-loop handoffs.

## Acceptance additions

- 256 dispatcher-level concurrent searches must equal a non-empty
  single-threaded reference and prove request-local determinism only.
- Keep the separate full-platform §14 Track J suite open.
- After deploy, rerun the original changed-since and four onboarding-query
  contamination probes, in addition to deployed SHA, exact-seven `/mcp`,
  rendered connector conversation, and organic-use/over-filter watch.

## Disposition

The proposal may proceed after these corrections and an exact-artifact Opus
review. Runtime edits, push, and archive remain gated until that review returns
APPROVE or all further ADAPT findings are resolved.

## Exact-artifact review

The 2026-07-24 exact-artifact Opus review returned **ADAPT** with three
classification-text corrections: blank audience is unset, audience comparison
is trimmed and case-insensitive, and a source page with an unrecognized
audience drives coordination ambient scope. All three are folded into the
spec, design, and RED-test tasks.

The independent Codex review also required changed-since category coverage,
public-wrapper coupling, parameterized visibility proof under every scope,
bounded response evidence without warning-log amplification, and a
discovery-only rendered acceptance that does not depend on deferred branch
authoring. Those corrections are folded as well. Runtime edits and push remain
gated on an exact re-review of these adapted artifacts.

## Final re-review disposition

Claude Opus 5 re-reviewed the exact adapted artifact set on 2026-07-24 and
returned **APPROVE**. It confirmed all ten combined Opus/Codex corrections,
strict OpenSpec validity, canonical requirement preservation, open taxonomy,
authority-before-relevance ordering, non-vacuous tests, unchanged exact
reads/list behavior, and same-lane sync/archive sequencing.

Its optional no-re-review-needed precision notes were folded: whitespace-only
scope is unset, scope notes count only candidates that would otherwise enter
the result set, the deferred public-wrapper category gaps are named, the
supported plugin generator is explicit, and tests guard against warning-log
amplification. This approval authorizes RED test and implementation work; it
does not claim that runtime code already exists.
