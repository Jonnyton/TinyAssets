# EarthOS Outreach Package — review before anything is sent

**Date:** 2026-06-18
**Decisions locked:** build his whole work-layer; outreach = submit via his form, then email.
**Status:** 10 workflows built/bound/published; one run live end-to-end. Drafts ready. Nothing submitted or emailed yet.

---

## 1. The artifact — a 10-workflow library on your platform (universe `earthos`, Goal `aa231afcf5cc`)

All reusable, bound to the Goal, gated by its provenance ladder. The 8 below are published/forkable; all run via `run_branch`.

| Workflow | ID | Covers |
|---|---|---|
| Source citation workflow ✅ run-proven | `989fd627007b` | ~15 source-verification missions |
| Local dataset locator | `5625c570901f` | find-data missions (ridership, water loss, property datasets) |
| Accountability source-pack | `65b144960c1a` | ownership & influence missions |
| Policy comparison matrix | `ad53249a8f73` | compare-policies missions |
| Summarize policy options | `214e76725d65` | response-layer / policy-review missions |
| Systems map | `229079746f3d` | systems-mapping missions |
| **Knowledge-graph gap detector** | `2f6c96b32cbd` | **his "AI-assisted gap detection" roadmap item** |
| Verify one transition signal source | `4a0d0b9fa6c7` | his Mission of the Week |
| Plain-language explainer | `edaad9a29fbc` | human-onboarding / explainer missions |
| Transition brief composer | `a1535363fd83` | his recurring brief (schedulable) |

Together these cover the majority of his 57-mission board and one roadmap *Future* item. They also form a loop: gap-detector proposes missions → citation/dataset/accountability workflows gather sourced evidence → policy/systems workflows turn it into responses → brief composer publishes the labeled state → gap-detector runs again. Catalog lives in the universe brain at `pages/workflows/earthos-workflow-library.md`.

## 2. Live run proof (real, sources verified)

`earthos_source_citation_workflow_v1` ran end-to-end (run `28edc1e4e1cc4980`, 4 nodes). Output, with citations spot-checked against the actual ABCWUA PDFs:

```
CLAIM: In Albuquerque, NM, ABCWUA reported that per-capita water use fell by ~50% from 1994 to 2017 under its conservation program.
DOMAIN: Water (ecological overshoot / access infrastructure)
PROVENANCE: source_linked
CITATION(S):
  - Water 2120: Water Conservation Plan Update — ABCWUA — March 2018 — https://www.abcwua.org/wp-content/uploads/Conservation_Rebates/2037_Water_Conservation_Plan.pdf — "reduction in per capita water use of 50% from 1994 - 2017"; GPCD "currently 128."  [VERIFIED]
  - Water 2120 Volume III — ABCWUA — Sept 2016 — https://www.abcwua.org/wp-content/uploads/Your_Drinking_Water-PDFs/Water_2120_Volume_III.pdf — "Per capita use has dropped almost 50% (251 gallons per person per day to 130 gpcd)."  [VERIFIED]
NOTE: Upgrades the signal from needs-source to source_linked — primary ABCWUA publications support the 1994→2017 comparison.
LIMITS: Supports the 2016–2018 reporting period, not "current" 2026 conditions without newer ABCWUA data.
```

Both quotes were confirmed verbatim against the source PDFs. Safe to share.

## 3. Draft — Submit Intelligence form (/contribute)

- **Source URL:** `https://www.abcwua.org/wp-content/uploads/Conservation_Rebates/2037_Water_Conservation_Plan.pdf`
- **Note:** "Water signal (Albuquerque): ABCWUA's 2018 Water Conservation Plan Update reports a 50% per-capita water-use reduction 1994–2017 (251→128 GPCD). Provenance: source_linked. Limit: historical comparison, not 2026-current. Generated with a reusable source-citation workflow — one of ~10 I built covering much of your mission board. Happy to share. — Jonathan"

## 4. Draft — founder email to geo.roessler@yahoo.com

> **Subject:** Built a starter work-layer for EarthOS — most of your mission board, ready to run
>
> Hi George,
>
> EarthOS Atlas stuck with me — the transition framing, abundance-paired-with-overshoot, "preparedness not prediction," and especially the provenance discipline. Most coherent version of that thesis I've seen.
>
> I build a domain-agnostic platform where people declare a goal and AI workflows pursue it, with evidence gates and a shared knowledge graph. Your roadmap — living ontology in a database, claimable missions, provenance grading, node federation, a contributor ledger — lines up almost one-to-one with primitives it already has.
>
> So rather than just say that, I built it. EarthOS now runs as a "universe" on my platform with ~10 reusable, provenance-graded workflows that cover most of your mission board — source verification, dataset finding, policy comparison, systems mapping, plain-language explainers, accountability source-packs, a transition-brief composer, and a knowledge-graph gap-detector (which is one of your own roadmap "Future" items). They're all built to run themselves.
>
> I ran the source-citation one end-to-end on a local claim. Output:
>
> [paste the citation record from section 2]
>
> I also dropped that source into your Contribute form. No ask here — the overlap was uncanny and I wanted to send something useful instead of a pitch. If you're curious, I'd happily give you access to run any of these yourself, share the workflow specs, or jump on a quick call. EarthOS could get the federation / missions / ledger parts of your roadmap close to for free.
>
> Either way — genuinely nice work.
>
> — Jonathan
> jonathan.m.farnsworth@gmail.com

## 5. What needs your go-ahead

1. **Run more of the library** for additional proof? (e.g., gap-detector on the current ontology, or the dataset-locator on a real ABQ need.) Optional; small provider cost each.
2. **Submit the Contribute form?** I can fill + submit via the browser on your ok.
3. **Email:** no mail connector wired — send from your own account (recommended), or I set up a Gmail connector.
4. **Edits** to the library, the email, or the citation record first.

---

## FINAL email (updated — all 10 workflows now run-proven)

> **Subject:** Built a starter work-layer for EarthOS — your mission board, running
>
> Hi George,
>
> EarthOS Atlas stuck with me — the transition framing, abundance-paired-with-overshoot, "preparedness not prediction," and especially the provenance discipline. Most coherent version of that thesis I've seen.
>
> I build a domain-agnostic platform where people declare a goal and AI workflows pursue it, with evidence gates and a shared knowledge graph. Your roadmap — living ontology in a database, claimable missions, provenance grading, city-node federation, a contributor ledger — lines up almost one-to-one with primitives it already has.
>
> So instead of just saying that, I built it. EarthOS now runs as a "universe" on my platform with ten reusable, provenance-graded workflows covering most of your mission board — source verification, dataset finding, policy comparison, systems mapping, plain-language explainers, accountability source-packs, a transition-brief composer, and a knowledge-graph gap-detector (one of your own roadmap "Future" items). I ran all ten end-to-end. They held real source discipline — citing actual IEA / ABCWUA / Jevons sources and refusing to invent the ones they couldn't verify.
>
> One worked example — the source-citation workflow on a local claim:
>
> CLAIM: Albuquerque per-capita water use fell ~50% from 1994 to 2017 under ABCWUA's conservation program.
> PROVENANCE: source_linked
> CITATIONS: Water 2120 Conservation Plan Update (ABCWUA, 2018) — "reduction in per capita water use of 50% from 1994-2017"; GPCD "currently 128." / Water 2120 Vol. III (ABCWUA, 2016) — "almost 50% (251 → 130 gpcd)."
> LIMITS: supports the historical comparison, not 2026-current conditions.
>
> I also dropped that source into your Contribute form. No ask here — the overlap was uncanny and I wanted to send something useful instead of a pitch. If you're curious, I'd happily give you access to run any of these yourself, share the workflow specs, or compare notes. EarthOS could get the federation / missions / ledger parts of your roadmap close to for free.
>
> Either way — genuinely nice work.
>
> — Jonathan
> jonathan.m.farnsworth@gmail.com
