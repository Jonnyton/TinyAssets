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
Physical-fabrication requests SHALL reference STL/STEP build outputs plus profiles under the commons license registry, declare a physical capability such as `fdm-print:0.4mm:PETG`, and bind photo/measurement QA gates. They SHALL obtain explicit total-first integer quotes so splitting quantity cannot earn a rounding advantage, use geography-aware deterministic seller ranking over haversine distance and declared shipping bands, and settle goods pro-rata to accepted units while paying shipping if any unit is accepted and refunding it only on total rejection. A seller outside every declared shipping band SHALL be ineligible rather than extrapolated.

#### Scenario: uncovered shipping is rejected before purchase
- **WHEN** no seller offer covers the buyer's destination band
- **THEN** the request returns no executable offer and locks no payment

### Requirement: Mechanical deliverables are reproducible parametric programs
For mechanical and code-CAD workflows, the canonical deliverable SHALL be OpenSCAD/CadQuery-class versioned source plus pinned toolchain/build instructions and generated STL/STEP hashes. A mesh or rendered preview alone SHALL not satisfy a source-artifact requirement. Before fabrication admission, the exact build SHALL pass declared printer-class gates for watertight/manifold geometry, minimum wall thickness, overhang/support, and clearance/tolerance; remix attribution SHALL follow source-code lineage.

#### Scenario: source, not mesh, is the remixable artifact
- **WHEN** a fabrication capability requires parametric source and a submission provides only an exported mesh
- **THEN** admission fails with the missing source and build contract named

### Requirement: Pricing-as-query keeps estimate stages distinct
Hardware price reads SHALL return three stages without conflation: commodity-module unit price, prototype shuttle-seat share from the allocation contract, and production mask-set NRE plus at-volume unit cost, each with source timestamps and `estimate: true`. Break-even SHALL use the canonical ceiling-rounded helper, and every public surface SHALL render the same versioned inputs and result.

#### Scenario: all surfaces agree on break-even
- **WHEN** the same price snapshot is read through MCP, HTTP, and website surfaces
- **THEN** each reports identical stage values, source timestamps, estimate flags, and break-even units

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
