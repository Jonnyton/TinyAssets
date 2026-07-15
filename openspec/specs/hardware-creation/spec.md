# Hardware Creation: Design to Silicon

## Purpose

The last layer of harness-to-hardware: users don't just rent hardware, they
design and fabricate it. Hardware creation is not a new platform — it is the
existing platform pointed at a new artifact class (design flows are workflow
graphs run as node work; sign-off is an outcome-gate ladder; sharing/remix is the
commons with Track G license composition; splitting mask cost is Track H pooling
via the multi-project-wafer shuttle; renting reconfigurable hardware is Track E
forwards with FPGA instruments).

Historical source of record (untouched): `docs/exec-plans/active/2026-07-08-track-i-hardware-creation.md`.
Shuttle economics (implemented): `tinyassets/paid_market/shuttle.py`.
Fabrication computations (implemented): `tinyassets/paid_market/fabrication.py`.
Composes: Tracks E (forwards), F (gates-as-verification), H (pools, apportionment), G (license propagation applies to IP blocks verbatim).

## Requirements

### Requirement: The accessible ladder, with an honesty clause binding on all copy

The system SHALL support the ladder I1 (FPGA tier — hardware's inference market,
and the mandatory proving ground: a design claims its FPGA-verified gate before
any shuttle accepts it), I2 (shuttle tier — pooled tape-outs via `allocate_shuttle`
with fractional ownership through Track H), and I3 (system tier — open
board/system designs as commons artifacts, fabrication brokered as paid requests).
Copy SHALL honor the honesty clause: democratized silicon means accessible nodes,
FPGAs, and open systems — not 3nm frontier accelerators, which remain gated by
fab access, capital, and export controls.

#### Scenario: a design must be FPGA-verified before a shuttle accepts it
- **WHEN** a design seeks a shuttle seat
- **THEN** it must first claim its FPGA-verified gate on tier I1
- **AND** copy never claims frontier-node access

### Requirement: Shuttle economics — knowable price, isolated failure (implemented)

`allocate_shuttle(die_area, total_cost, operator_fee_ppm, design_areas)` SHALL
apportion cost area-proportionally via largest-remainder with conservation
asserted. It SHALL use a full-die cost basis: each design pays `cost × area/die`
regardless of fill, so a design's price is knowable at signup and dropping a
failed design never raises survivors' prices. A minimum-fill viability check
(default 50%) SHALL reschedule a hollow shuttle rather than run it. Risk split:
a design failing its own gates owes nothing (dropped pre-mask); the shuttle
failing in fab is shared risk with a full refund through the pool machinery.

#### Scenario: dropping a failed design never raises survivors' prices
- **WHEN** a design is dropped pre-mask for failing its own gates
- **THEN** it owes nothing but time
- **AND** the surviving designs' prices are unchanged (full-die cost basis)

### Requirement: Verification chain mints a hardware capability

Sign-off gates SHALL be EDA runs with attested artifacts (DRC report hash, timing
report, FPGA test-bench evidence URL) using the same evidence pattern as gates
today. Post-fab bring-up results SHALL claim the final "silicon validated" gate,
and validated designs SHALL mint a hardware capability (reference design +
characterization data + license terms), immediately remixable in the commons with
attribution and appearable as a hardware class in Track E/F instruments.

#### Scenario: a validated design becomes a market hardware class
- **WHEN** a design passes bring-up and claims "silicon validated"
- **THEN** it mints a hardware capability with characterization data and license terms
- **AND** it can appear as a hardware class in Track E/F instruments

### Requirement: Physical fabrication reuses commons + gates + exact quoting (implemented)

Designs (STL/STEP + profiles) SHALL be commons artifacts under Track G's CC
registry; print capacity SHALL sell as paid requests with physical capabilities
(e.g. `fdm-print:0.4mm:PETG`); physical QA SHALL be a gate ladder with
photo/measurement evidence. The three new computations SHALL be implemented in
`fabrication.py`: exact print-job quoting (total-first math so quantity splits
earn no rounding advantage), geography-aware seller ranking (haversine → declared
shipping bands → deterministic ordering; outside-all-bands is excluded, never
extrapolated), and per-unit acceptance settlement (goods pro-rata to accepted
units; shipping paid if any unit accepted, refunded only on total rejection).

#### Scenario: a seller outside all shipping bands is excluded, not extrapolated
- **WHEN** a candidate seller falls outside every declared shipping band
- **THEN** it is excluded from ranking
- **AND** its effective cost is never extrapolated

### Requirement: Mechanical designs are parametric programs, not meshes (binding)

Commons hardware artifacts SHALL be code-CAD source (OpenSCAD/CadQuery-class);
STL/STEP SHALL be build outputs, never the artifact. Remix SHALL be forking the
source; attribution SHALL flow through code lineage. Printable sign-off gates
(watertight/manifold, minimum wall thickness, overhang/support, clearance/tolerance
against the declared printer-class capability) SHALL be claimed before any
fabrication job accepts the design.

#### Scenario: the artifact is the source, not the mesh
- **WHEN** a user remixes a mechanical design
- **THEN** they fork the code-CAD source and the mesh is regenerated as a build output
- **AND** attribution flows through code lineage

### Requirement: Pricing-as-query returns three un-conflated stages with a pinned break-even

Fabrication pricing SHALL be a read primitive: quotes without commitment,
consumable during design conversations. The silicon quote SHALL return three
stages, never conflated: (1) commodity module unit price, (2) prototype
shuttle-seat share via `allocate_shuttle`, (3) production mask-set NRE with
at-volume unit cost. Break-even SHALL be computed by the pinned `break_even_units`
(ceil; None when custom never wins) so every surface states the identical number.
Every quote payload SHALL carry `estimate: true` plus sources.

#### Scenario: every surface states the identical break-even number
- **WHEN** a break-even is shown in a universe conversation, a curve endpoint, or the investor demo
- **THEN** all surfaces state the identical number from the pinned `break_even_units`
- **AND** the quote payload carries `estimate: true` and its sources

### Requirement: Garage silicon is a device market and a learning ladder, not a compute market

All copy SHALL honor this extended honesty clause verbatim, and garage silicon SHALL be treated as a device market and a learning ladder, NOT a compute market:

Extended honesty clause (binding on all copy): garage processes reach ~1–10μm —
hundreds-to-thousands of transistors: analog, sensor front-ends, MEMS-class
devices, photodetectors, educational/prototype silicon. Garage silicon is a
device market and a learning ladder, NOT a compute market — modern accelerators
sit seven orders of magnitude away behind physics-and-capital walls. Compute-class
silicon remains the pooled-shuttle → production-mask path. Any claim otherwise is
prohibited copy.

#### Scenario: garage-litho copy never claims compute-class silicon
- **WHEN** copy describes garage-fab capabilities
- **THEN** it frames them as a device market and learning ladder
- **AND** it routes compute-class silicon to the pooled-shuttle to production-mask path

### Requirement: Garage-fab listings carry a fail-closed safety-documentation gate (REQUIRED)

Real fab chemistry involves HF and dopants. Garage-fab capability listings SHALL
carry a safety-documentation gate (process chemistry declared; HF-minimized /
spin-on-dopant processes strongly preferred per Hacker Fab practice) the same way
printables carry geometry gates. Democratizing lithography must not democratize
chemical accidents; listings without safety documentation SHALL fail closed.

#### Scenario: a garage-fab listing without safety documentation is blocked
- **WHEN** a `litho:*` capability is listed without declared process-chemistry safety documentation
- **THEN** the listing fails closed (not published)
- **AND** an HF-minimized / spin-on-dopant process is strongly preferred when documented

## Open founder decisions

- **Shuttle minimum-fill** (Track I §2): the minimum-fill viability threshold
  (default 50%) below which a shuttle reschedules rather than runs is pending
  founder confirmation.
- **Appliance carrier: in-house vs bounty** (§3e): whether the demo-blocking
  "appliance carrier rev-1" commons hardware capability is built in-house on the
  platform (recommended, dogfooding) or bounty-first is a founder decision, may
  swap by timeline.
