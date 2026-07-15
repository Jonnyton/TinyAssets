# Track I — Hardware Creation: Design to Silicon

**Date:** 2026-07-08
**Author:** founder + Claude (design session)
**Status:** Dispatch-ready design spec. Shuttle economics implemented and tested (`tinyassets/paid_market/shuttle.py`; 125-test suite total). Composes Tracks E (forwards), F (gates-as-verification pattern), H (pools, apportionment), G (license propagation applies to IP blocks verbatim).
**Mission close:** this is the last layer of "harness to hardware" — users don't just rent hardware; they design and fabricate it.

---

## 0. The insight that makes this cheap to build

Hardware creation is not a new platform — it is the existing platform pointed at a new artifact class:

| Hardware need | Existing TinyAssets primitive |
|---|---|
| Design flow (synthesis → place&route → DRC/LVS → timing) | A workflow graph; open EDA (OpenLane/OpenROAD) runs are **node work sold on the Track E compute market** |
| Design sign-off ("passes DRC", "closes timing @ 50MHz", "verified on FPGA") | An **outcome-gate ladder**, machine-checkable |
| Sharing/remixing designs and IP blocks | The **commons**, with Track G license composition applied verbatim (an unregistered-license IP block blocks tape-out, fail-closed) |
| Splitting a six-figure mask cost across strangers | **Track H pooling** — and the hardware industry already invented it: the multi-project-wafer shuttle |
| Renting reconfigurable hardware by the hour | **Track E capacity forwards** with FPGA instruments |

## 1. The ladder (and the honesty clause)

- **I1 — FPGA tier:** hardware's inference market. Sellers post FPGA-class capacity forwards (`part-class × window`); designs deploy as bitstreams; this is also the mandatory proving ground — a design claims its "FPGA-verified" gate before any shuttle accepts it.
- **I2 — Shuttle tier:** pooled tape-outs on accessible nodes (the 130nm–28nm shuttle ecosystem, Tiny-Tapeout-style tile programs at the entry level). Fractional ownership of resulting silicon via Track H; per-design costs via `allocate_shuttle`.
- **I3 — System tier:** open board/system designs (accelerator cards, open server designs) as commons artifacts with BOM manifests; fabrication is ordinary contract-manufacturing brokered as paid requests.

**Honesty clause (mirrors Track F §1):** democratized silicon means accessible nodes, FPGAs, and open systems — not 3nm frontier accelerators, which remain gated by fab access, capital, and export controls. The claim is that the whole *accessible* ladder becomes designable, fundable, verifiable, and ownable by anyone — and that the ladder's top keeps rising as open flows mature.

## 2. Shuttle economics (implemented)

`allocate_shuttle(die_area, total_cost, operator_fee_ppm, design_areas)`:
- exact area-proportional cost via largest-remainder apportionment; conservation asserted
- **full-die cost basis:** each design pays `cost × area/die` regardless of fill — unfilled area is the operator's inventory risk, so a design's price is knowable at signup and dropping a failed design never raises survivors' prices (tested)
- minimum-fill viability check (default 50%): a hollow shuttle reschedules rather than running
- **risk split, stated on the tin:** your design failing its own gates costs you nothing but time (dropped pre-mask, owes nothing); the shuttle failing in fab is shared risk → full refund through the pool machinery. This split is what makes pooled silicon safe for first-time designers.

## 3. Verification chain

Sign-off gates are EDA runs with attested artifacts (DRC report hash, timing report, FPGA test-bench evidence URL) — the same evidence pattern as gates today. Post-fab, bring-up results claim the final gate ("silicon validated"), and validated designs mint a **hardware capability** in the registry: reference design + characterization data + license terms, immediately remixable in the commons with attribution. A validated open accelerator design can then appear on the *other* side of the platform — as a hardware class in Track E/F instruments. The loop closes: the market's buyers eventually run on hardware the market's users designed.

## 3b. §I4 — Physical fabrication & the builder community (implemented)

The maker/3D-printing community is the system tier made real — and the proof of the model: open design commons, remix-with-attribution culture, CC licensing, and distributed print farms evolved organically for fifteen years without a settlement layer. TinyAssets formalizes what they already practice. Designs (STL/STEP + profiles) are commons artifacts under Track G's existing CC registry; print capacity sells as paid requests with physical capabilities (`fdm-print:0.4mm:PETG`); physical QA is a gate ladder with photo/measurement evidence. Three computations were genuinely new and are implemented in `fabrication.py`: exact print-job quoting (mg/seconds/micros, total-first math so quantity splits earn no rounding advantage), geography-aware seller ranking (haversine → declared shipping bands → deterministic effective-cost ordering; outside-all-bands = excluded, never extrapolated), and per-unit acceptance settlement (goods pro-rata to accepted units; shipping paid if any unit accepted, refunded only on total rejection; reputation flag not collateral — spot fab keeps the cooperative-trust posture). Builders also physically close the loop: they print the frames, ducts, and enclosures of the open hardware (§3) that sells capacity back into the market — RepRap's self-replication vision with an economic layer under it.

## 3c. §I5 — Mechanical design flows: code-CAD (amended 2026-07-09)

**Shape decision (binding): mechanical designs are parametric programs, not meshes.** Commons hardware artifacts are code-CAD source (OpenSCAD/CadQuery-class); STL/STEP are BUILD OUTPUTS, never the artifact. This makes hardware design behave identically to everything else on the platform: remix = fork the source, diffs are reviewable, attribution flows through code lineage, a vibe coder describes the object ("flip-open book, two screens") and the universe writes the program, and a hardcore user edits the hinge-clearance parameter by hand. Design sessions are ordinary workflow graphs whose nodes run open CAD kernels as ordinary (priceable) node work.

**Sign-off gates for printables** (machine-checkable, existing gates machinery): watertight/manifold · minimum wall thickness for declared material · overhang/support analysis · clearance/tolerance check against the declared printer-class capability (`fdm-print:0.4mm:PETG`). A design claims its "printable" gate before any fabrication job accepts it — the mechanical mirror of §3's DRC/LVS ladder.

## 3d. §I6 — Pricing-as-query (amended 2026-07-09)

Fabrication pricing is a **read primitive**: quotes without commitment, consumable during design conversations (same posture as the Track E spot quote — cheap, cacheable, honest about being an estimate). The silicon quote returns THREE stages, never conflated: (1) commodity module unit price (live fabrication-market quotes); (2) **prototype** shuttle-seat share (validation dies — thousands of dollars, via `allocate_shuttle` over open pools); (3) **production** mask-set NRE (tens of thousands, mature node) with at-volume unit cost. Break-even is computed by the pinned `break_even_units` (ceil; None when custom never wins) so every surface — universe conversations, curve endpoints, the investor demo — states the identical number. Every quote payload carries `estimate: true` + sources.

## 3e. Commons carrier reference (seeding, demo-blocking)

The "appliance carrier rev-1" must exist as a real commons hardware capability before the demo: SoM socket (RK3588/Orin-class), dual DSI, far-field mic + speaker, lid hall sensor, USB-C PD. **Recommended path: build in-house on the platform itself (goal + gate ladder, CC0, attributed to its actual designer), then open a community bounty for rev-2** — dogfooding the exact flow the demo narrates, with the receipts captured as demo material. Founder may swap to bounty-first if timeline allows.

## 3f. §I7 — Garage fab: the ladder's last rung (amended 2026-07-09)

**Existence proof:** garage lithography is real — Zeloof-class home fabs (1,200-transistor chips on ~10μm polysilicon via a DIY maskless stepper) and **Hacker Fab** (open-source, reproducible DIY semiconductor process: published BOMs for few-$k steppers, spin coaters, tube furnaces; university chapters replicating the toolchain). It is a living commons with NO economy attached — precisely the gap this platform fills.

**Extended honesty clause (binding on all copy):** garage processes reach ~1–10μm — hundreds-to-thousands of transistors: analog, sensor front-ends, MEMS-class devices, photodetectors, educational/prototype silicon. **Garage silicon is a device market and a learning ladder, NOT a compute market** — modern accelerators sit seven orders of magnitude away behind physics-and-capital walls. Compute-class silicon remains the pooled-shuttle → production-mask path (§I2, §I6). Any claim otherwise is prohibited copy.

**Three platform plays:**
1. **Equipment commons (the recursive one).** Fab tools ARE Track I §I5 artifacts — code-CAD + BOM + firmware — buildable by the existing maker community with printers and CNC, sold as fabrication jobs, gated by characterization ladders ("resolves 5μm," verified with evidence). Makers fabricate fab capacity for each other: the fab that prints itself, one level below RepRap. LumenPnP-class open pick-and-place already proves the pattern at the PCB-assembly rung.
2. **Garage fab as a first-ever market.** Capability listings like `litho:5um:analog` sell custom sensors, teaching wafers, and prototype analog to buyers who could never justify a foundry MPW seat for a five-device experiment. Small, novel, defensible: this market has never existed anywhere.
3. **The complete ladder, no gaps:** printer → CNC → PCB etch → open pick-and-place → board products (carrier, §3e) → FPGA (§I1) → open EDA (§1) → garage litho for niche devices (§I7) → pooled shuttles (§I2) → production masks (§I6). Every rung community-buildable or community-poolable; each rung the proving ground for the next; the honesty clause marks exactly where the garage ends and the pool begins.

**Safety gate (REQUIRED, joins OPERATING-NOTES §3):** real fab chemistry involves HF and dopants. Garage-fab capability listings carry a safety-documentation gate (process chemistry declared; HF-minimized / spin-on-dopant processes strongly preferred per Hacker Fab practice) the same way printables carry geometry gates. Democratizing lithography must not democratize chemical accidents; listings without safety documentation fail closed.

## 4. Waves

| Wave | Ships | Depends on |
|---|---|---|
| I-W1 | EDA flows as commons graphs + sign-off ladders; FPGA instruments · **code-CAD mechanical flows + printable gate ladder (§I5)** · **pricing-as-query (§I6)** · **seed appliance carrier rev-1 (§3e)** | E-W4 forwards |
| I-W2 | Shuttle pools: `allocate_shuttle` + Track H funding + fab-failure refund path | H-W1 |
| I-W3 | Hardware capability minting; IP-block licensing via Track G; system tier | G-W1, I-W2 |
| I-W4 | Garage-fab tier (§I7): equipment-commons seeding (stepper/spin-coater/furnace as code-CAD artifacts), `litho:*` capability class + characterization ladders + safety gate | I-W3 |

## 5. Out of scope

Operating fabs or shuttle logistics (partner integrations); frontier-node access; export-control compliance tooling (legal gate before I-W2 ships across borders); EDA tool development itself; hardware warranty/insurance.

---

*Session close (2026-07-08): harness → models → inference → training → capital → data → hardware creation. Every layer specced (Tracks E–I), every exactness-critical computation implemented and adversarially disciplined — 8 modules, 125 tests, all conservation-swept. This spec is the last one this session should produce; the stack's bottleneck is now entirely execution: land the core, fix P0/P1, ship Wave 2.*
