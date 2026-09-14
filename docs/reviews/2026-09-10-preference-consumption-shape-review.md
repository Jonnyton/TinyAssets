# Preference consumption and activation shape review

September10 2026. Claude session59767 ended exit0 ADAPT358s, read-only, no tests.
Reviewed docs940cadd6 plus the binding-access paragraph. Full substantive verdict
recovered from transcript3a868f0c-2500-4abd-b573-b5cb270a0703 after hook recap.

Verified: no production AgentModelPlan producer; converse passes no selection;
public bind payload accepts only provider; set_serving refuses manifest assignments.
Existing owner/member custody and request validation are the correct reuse seams.

Six required corrections incorporated in runtime-preference-consumption.md:

1. Native-default selected-member launch must bypass HTTP discovery and retain
   native custody, with request ceiling based on actual serving authority unless
   an explicit allowed_providers ceiling exists.
2. Native catalog entries must actually be produced from the current registry,
   custody and availability, preserving the Claude-serving opt-in.
3. Home-only preference guard must not break non-home legacy turns. Explicit
   overrides outside supported scope refuse, not silently fall back.
4. Override ModelPolicy construction uses exactly its own primary/tail and the
   observed saved generation; provenance is separate from generation.
5. Change the runner to reject contradictory incoming selection and plan.
6. Specify both public binding model_access and converse model_choice contracts.
   Delta specs now record these; deposit/onboarding stays legacy until opt-in.

Non-gating follow-ups: inventory every served-turn sink before activating manifests;
avoid duplicated discovery IO without weakening post-IO fences; native first
candidate has no whole-turn fallback traversal yet; readiness discovery may occur
under the existing gesture lock but never a SQLite transaction; reconcile seven
release commits on origin/main before landing. Some contain extracted versions of
code already in this feature, so no blind rebase of the dirty/untracked reset work.
The scoped-reset inventory defect remains independent and unresolved.

This is shape approval with required adaptations, not implementation approval.
Native discovery evidence was collected afterward and has not received its
source-derived implementation review. No new production activation or deployment.
