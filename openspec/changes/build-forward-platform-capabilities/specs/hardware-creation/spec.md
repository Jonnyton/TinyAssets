## ADDED Requirements

### Requirement: Hardware creation follows a verified accessible ladder
Hardware workflows SHALL support the complete I1/I2/I3 ladder: I1 is FPGA capability rental and the mandatory FPGA-verified proving gate before shuttle admission; I2 is pooled tape-out through canonical shuttle allocation with fractional ownership under pooled-training/ownership rules; I3 is open board and system design as commons artifacts with fabrication brokered as paid requests. Evidence for each stage SHALL bind to the exact design version. Product copy SHALL describe accessible nodes, FPGAs, and open systems honestly and SHALL NOT imply access to frontier 3nm-class accelerators constrained by fab access, capital, or export controls.

#### Scenario: an unverified design cannot enter a shuttle
- **WHEN** a design lacks the required passing prototype gate for its exact source hash
- **THEN** shuttle admission is rejected before seat allocation or payment lock

### Requirement: Shuttle lifecycle uses canonical total-first arithmetic
A shuttle SHALL publish full-die cost, usable area, operator fee, minimum fill, schedule, and cancellation terms before accepting seats. Admission and settlement SHALL use or explicitly modify the canonical `paid-market-economy` oracle; the future lifecycle SHALL freeze each accepted design's full-die-rate price so dropping a pre-mask gate failure does not raise survivors' prices. A design failing its own DRC/LVS/timing or other sign-off gate SHALL owe nothing and lose only its work; a shuttle failing in fabrication SHALL be shared risk with a full pool refund. A run below its configured minimum fill SHALL reschedule or refund under frozen terms.

#### Scenario: failed design removal is isolated
- **WHEN** one admitted design is removed before tape-out while the shuttle remains viable
- **THEN** survivors retain their original allocated prices and the removed design follows its declared refund rule

### Requirement: Verified bring-up mints a hardware capability
A completed fabrication alone SHALL NOT mint a sellable hardware capability. Sign-off SHALL bind attested DRC report hash, timing report, FPGA test-bench evidence, exact design, manufacturing evidence, bring-up results, and test procedure before the final `silicon validated` gate can pass. The minted capability SHALL include the reference design, characterization data, and composed license terms; it SHALL be immediately remixable in the commons with attribution and eligible to appear as a hardware class in price/forward and training instruments.

#### Scenario: validated hardware becomes a market class
- **WHEN** fabrication and every required bring-up gate pass for a design version
- **THEN** the system mints an immutable capability record referencing the design and evidence hashes

### Requirement: Physical fabrication composes artifacts, gates, shipping, and exact settlement
Physical-fabrication requests SHALL reference STL/STEP build outputs plus profiles under the commons license registry, declare a physical capability such as `fdm-print:0.4mm:PETG`, bind photo/measurement QA gates, and validate their own fabrication descriptor facets — process and material families, tolerance and size capability, inspection or certification class, and declared service-region and shipping bands. Acceptance, inspection, delivery, cure, and rejection semantics are owned here.

This capability SHALL NOT re-implement the arithmetic or the published quote. Exact total-first integer quotation, distance as a pure numeric helper, exclusion of offers matching no declared shipping band, deterministic seller ranking, and conserved settlement across accepted units, rejected units, shipping disposition, treasury fee, seller net, and buyer refund are already canonical pure oracles in `paid-market-economy` and SHALL be called or differential-tested against, never duplicated. Executable landed totals, indicative-versus-firm quote provenance, freshness, public quote reads, and economic routing belong to `paid-market-live-price-discovery`. Hardware supplies the domain facts and the acceptance outcome; the oracle computes; the discovery surface publishes.

#### Scenario: uncovered shipping is rejected before purchase
- **WHEN** no seller offer covers the buyer's destination band
- **THEN** the request returns no executable offer and locks no payment

#### Scenario: fabrication arithmetic comes from the canonical oracle
- **WHEN** a fabrication request needs a quote, a ranking, or a settlement split
- **THEN** it calls the canonical `paid-market-economy` helpers, or proves equality against them by differential test, rather than computing its own totals

### Requirement: Mechanical deliverables are reproducible parametric programs
For mechanical and code-CAD workflows, the canonical deliverable SHALL be OpenSCAD/CadQuery-class versioned source plus pinned toolchain/build instructions and generated STL/STEP hashes. A mesh or rendered preview alone SHALL not satisfy a source-artifact requirement. Before fabrication admission, the exact build SHALL pass declared printer-class gates for watertight/manifold geometry, minimum wall thickness, overhang/support, and clearance/tolerance; remix attribution SHALL follow source-code lineage.

#### Scenario: source, not mesh, is the remixable artifact
- **WHEN** a fabrication capability requires parametric source and a submission provides only an exported mesh
- **THEN** admission fails with the missing source and build contract named

### Requirement: Pricing-as-query keeps estimate stages distinct
Hardware SHALL define three domain stages that a price read must never conflate: commodity-module unit price, prototype shuttle-seat share from the allocation contract, and production mask-set NRE plus at-volume unit cost. For each stage it SHALL supply the domain inputs and the evidence that justifies them. Break-even SHALL come from the canonical ceiling-rounded `paid-market-economy` helper, which returns no break-even when per-unit margin is non-positive. Publication of those stages — source timestamps, `estimate: true` provenance separating indicative references from executable firm offers, freshness bounds, and identical rendering across every public surface — is owned by `paid-market-live-price-discovery`; hardware SHALL consume that contract rather than defining a parallel one.

#### Scenario: all surfaces agree on break-even
- **WHEN** the same price snapshot is read through MCP, HTTP, and website surfaces
- **THEN** each reports identical stage values, source timestamps, estimate flags, and break-even units

#### Scenario: a hardware estimate is never published as a firm offer
- **WHEN** a hardware stage value is derived from indicative inputs rather than an executable offer
- **THEN** the discovery surface marks it indicative under its quote-provenance rules and no purchase path treats it as executable

### Requirement: Garage-fabrication copy is capability-honest
Garage lithography and similar roughly 1–10µm, hundreds-to-thousands-of-transistor processes SHALL be listed as analog, sensor-front-end, MEMS-class, photodetector, educational, or prototype-device capabilities supported by their evidence. Copy SHALL state that modern accelerators remain roughly seven orders of magnitude away behind physics and capital constraints, and SHALL route compute-class silicon through the pooled-shuttle then production-mask path rather than marketing garage processes as compute.

#### Scenario: unsupported compute claim is blocked
- **WHEN** a garage-fabrication listing claims compute-class output without the required evidence gate
- **THEN** publication is rejected with the unsupported claim identified

### Requirement: Garage-fabrication listings require safety documentation
Any listing tagged with a regulated or hazardous fabrication process SHALL bind current process-chemistry, handling, ventilation, waste, emergency, and jurisdictional documentation. HF-minimized and spin-on-dopant processes SHALL be strongly preferred and surfaced when supported by the documentation. Missing or expired required documentation SHALL fail closed before discovery or purchase.

#### Scenario: missing safety evidence blocks a listing
- **WHEN** a garage-fabrication listing lacks any required safety document for its declared process
- **THEN** the listing remains unavailable and names the missing evidence
- **AND** documented HF-minimized or spin-on-dopant alternatives are preferred when available
