# Exact storage/reset checkpoint release question

Review the frozen commit containing this file. This is a bounded, dark
implementation checkpoint under the approved turn contract and reset disposition,
not the completed adapter. Read `storage-checkpoint.md`, `storage-lock-order.md`,
`reset-integration.md`, then the four canonical runtime files and two tests named
there. Generated plugin copies must match; no general repo audit, broad suite,
subagents, provider/network calls or user-account activity.

Question: is this storage/retention/reset boundary safe to integrate with the
common file/cloud worker while it remains unexposed, or is a basic correctness/
privacy/authority defect present? Explicitly distinguish missing next-stage
adapter work from a defect in the implemented checkpoint.

1. Can same-key races/reconnects ever create a second run, reinterpret mutable
   context as caller intent, expose another owner's turn, or replay effects?
2. Does the two-DB pair/flag repair dedupe across the actual crash window, refuse
   reconstruction after trimming/deletion/reset, and retain only necessary identity?
3. Is the lock order reset shared barrier -> author writer -> one subordinate
   writer safe with existing deletion and service-wide leases? No provider lock,
   network, new writer/connection under shared prepared fences, or automatic reset
   recovery is permitted in a consumer callback.
4. Are source authorization and exact active/hash checks sufficient before snapshot
   use without adding a blanket ban on reusable public prompt definitions?
5. Does the reset action preserve existing authority, validate scope/schema/identity,
   recover post-witness expiry before serving, retain pre-witness rollback, and
   preserve unrelated admissions and legacy plan semantics? Existing home DBs
   remain refused; do not request an expansion to make that test green.

Return APPROVE / ADAPT / BLOCK plus structured AGREE / DISAGREE_EVIDENCE with code
citation / DISAGREE_CONCERN findings. Reserve final minute for verdict. Treat the
three recorded Linux failures as baseline fixture evidence, not new regressions;
confirm the fixes preserve the actual safety assertions. No live proof claimed.
