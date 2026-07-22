# Spec: Chatbot-Built RISC-V/FPGA Physical Vertical Proof v0

**Status:** paused as first-device candidate; host proposed conversational
cookbook pivot on 2026-07-15  
**Approved direction:** 2026-07-15  
**Host clarification:** 2026-07-15 — the build must originate, be steered, and
complete through a real chatbot conversation using the live connector  
**Implementation authority:** none until this specification is approved  
**Candidate successor:**
`ideas/2026-07-15-conversational-cookbook-device.md`  
**Research review gate:** a Claude-family reviewer must independently re-check
the external sources and TinyAssets composition before any build, purchase,
push, or acceptance run based on this specification.

## Objective

Let a user start with an ordinary chatbot conversation through the installed
TinyAssets connector and end with one physically undeniable, user-owned,
remixable computing artifact. The connector conversation—not a developer
preparing a hidden repository—is the product entry point and control surface.

The first artifact is an **offline voice-command computer/module**:

- a RISC-V soft CPU and custom ML accelerator implemented in FPGA gateware;
- a daemon-trained or fine-tuned, quantized keyword-spotting model;
- a custom carrier PCB with power, FPGA-module connection, digital microphone,
  USB data/debug, and visible status output;
- open firmware and host-side test tooling;
- physical evidence that the released board cold-boots and performs inference
  on the FPGA system without cloud or host inference.

The first proof optimizes for closure, observability, and reproducibility—not
desktop-class performance. It can be embedded in a robot, instrument, toy, or
appliance to recognize a small user-chosen vocabulary and emit a digital
command over GPIO/USB/UART. It demonstrates conversational design sovereignty
and vendor-mediated manufacturing. It does not claim local semiconductor
fabrication or supply-chain independence.

### What the device is

In plain language, it is a small circuit board that listens through a
microphone for a handful of words such as `tiny`, `start`, `stop`, `left`, and
`right`. A RISC-V CPU implemented inside the reprogrammable FPGA coordinates
the device. A second circuit designed in the FPGA accelerates the slowest part
of the neural-network inference. LEDs and a low-voltage digital interface show
or transmit the recognized command.

It is **not** a desktop computer, a general chatbot, or a new fabricated chip.
The ECP5 FPGA silicon is purchased. What is novel is the user-directed system
assembled around it: the behavior, model, accelerator circuit, SoC
configuration, carrier PCB, firmware, tests, and evidence.

### User and job

The first user interacts through a normal chatbot UI with the TinyAssets
connector installed. They may own hobbyist machines and an electronics bench,
or authorize bounded vendors and specialists. They are not required to edit
RTL, KiCad files, firmware, or shell commands directly. Their job is:

> Tell my chatbot what physical device I want, steer its important design
> decisions, approve money and irreversible actions, and receive a working,
> inspectable device whose model, gateware, PCB, firmware, lineage, build
> receipts, and measurements were produced and revised through daemon Branches.

### Connector-first build journey

The proof begins from a new conversation in a real supported chatbot—not from
a pre-populated hardware repository. Through the live connector:

1. the user describes the wanted behavior in ordinary language;
2. the connector creates a Goal and an initial design Branch;
3. the chatbot presents comprehensible choices for vocabulary, interfaces,
   form factor, privacy, performance, purchased inputs, and budget;
4. the user chooses or revises those decisions in conversation;
5. daemons create, test, and compare design artifacts while the chatbot reports
   progress and failures in user language;
6. every purchase, fabrication order, machine action, and unsafe or
   irreversible boundary returns to the conversation for approval;
7. physical test evidence is attached to the same Goal and evaluated; and
8. the chatbot publishes the passing design as discoverable remixable units.

The daemon may run asynchronously and the user may resume in later chat
sessions. “Built through a conversation” means the durable Goal remains
discoverable through the connector and all material decisions, approvals,
Branch changes, failures, and acceptance evidence are visible there. It does
not require one uninterrupted chat window.

A privacy-preserving conversation receipt records message/action identifiers,
user decisions, approvals, Branch revisions, and evidence links. The raw
private transcript is not made public by default.

### Product demonstration

After a power-off interval, the released board must:

1. boot from nonvolatile storage without JTAG intervention;
2. identify the board revision, gateware hash, firmware hash, and model hash
   over USB serial;
3. accept live audio from its digital microphone;
4. classify a bounded command vocabulary with the model executing on the
   RISC-V/FPGA system;
5. emit the predicted class, confidence/score, inference cycles, and elapsed
   time over USB/UART;
6. execute the user's safe low-voltage output mapping over LED/GPIO; and
7. visibly indicate at least two classes on-board.

## Scope Decisions

### Chosen vertical slice

- **Compute:** purchased open ECP5-class FPGA module with sufficient logic,
  flash, and RAM; module SKU is selected during planning after availability and
  physical module-interface review.
- **CPU/SoC:** LiteX-compatible RISC-V soft CPU, with CFU-Playground used as the
  reference full-stack accelerator framework.
- **Accelerator:** one custom function unit accelerating a measured model
  bottleneck. The daemon must profile before choosing the kernel.
- **Model:** small quantized keyword-spotting network trained or fine-tuned from
  a recorded, licensed dataset. Initial vocabulary may use TensorFlow Speech
  Commands; local recordings form a separate live-use set.
- **PCB:** a custom carrier, not a rebadged development board. It owns USB-C
  power/data, microphone, status LEDs, test points, protection, and the
  FPGA-module interface.
- **Toolchain:** open-source FPGA path wherever the selected module supports it:
  LiteX, Verilator/Renode, Yosys, nextpnr, and the applicable open bitstream
  project. KiCad owns PCB source and fabrication exports.
- **Runtime:** bare-metal or RTOS firmware. Linux is explicitly not required.

The replaceable module boundary is intentional. Requiring a raw BGA FPGA,
high-speed RAM layout, and power-tree design on revision A would test PCB
manufacturing risk more than daemon-driven full-stack composition. A later
revision may collapse the module onto the main PCB after proof v0 passes.

### Purchased-input boundary

Permitted purchased inputs must be listed in `evidence/purchased-inputs.yaml`:

- FPGA module and every electronic component;
- PCB fabrication and assembly services;
- microphone, connectors, enclosure material, cables, and programmers;
- lab instruments and fixtures;
- training compute and storage;
- shipping, packaging, and specialist market work.

Purchased source designs, proprietary model weights, undocumented FPGA IP, and
closed generated gateware are not permitted in the released proof. A required
vendor tool may be used only if an open-source path proves unavailable and the
host approves the exception before purchase; the exception prevents a claim of
fully open reproducibility.

## TinyAssets Domain Model

This is a **user project**, not TinyAssets platform infrastructure. Its Branch
is published as a remixable design in the commons and bound to a physical-proof
Goal in the builder's universe. Project source belongs in a separate user-owned
repository; TinyAssets core should receive no FPGA-, PCB-, or model-specific
primitive.

The Branch is not one indivisible zip file. It is a dependency graph of typed,
versioned design units so another chatbot can reuse the board while changing
the model, reuse the model while targeting another FPGA, or reuse the complete
device while changing only its behavior.

### Actors

- **User:** originates the project, makes or accepts material design decisions,
  contributes optional data/artifacts, approves purchases and irreversible
  effects, and owns their resulting Branch under the selected licenses.
- **Chatbot + connector:** translates between ordinary conversation and the
  Goal, Branch, design-unit, evidence, approval, and market surfaces. It is the
  user's complete control plane, not merely a final report viewer.
- **Design daemon:** owns branch execution and artifact integration.
- **Independent evaluator:** compares outputs to locked tests and measurements;
  it does not generate candidate designs.
- **Machine/vendor executor:** runs synthesis, PCB fabrication/assembly, or lab
  procedures under explicit authority.
- **Instrument:** produces ground-truth measurements and signed/timestamped raw
  evidence where possible.

### Branch composition

The reference Branch consists of ordinary nodes or sub-Branches:

1. accept the user's natural-language request through the live connector;
2. create the Goal, initial Branch, and attribution/lineage ledger;
3. conversationally freeze behavior, requirements, and purchased-input policy;
4. train/fine-tune and quantize the model;
5. generate locked golden vectors and a CPU-only baseline;
6. profile the baseline and select one accelerator kernel;
7. design CFU gateware, SoC integration, and firmware;
8. run unit tests, co-simulation, synthesis, timing, and resource checks;
9. design the carrier PCB and run ERC/DRC/manufacturing checks;
10. present a procurement packet in chat and request user approval;
11. receive/inspect/assemble hardware through an authorized user, machine, or
    vendor executor;
12. run rail-first bring-up, program, cold-boot, and hardware-in-loop tests;
13. compare physical results to the locked evaluator and revise until they
    pass;
14. publish the passing design units and evidence through the connector; and
15. prove downstream reuse with a second user's connector-driven physical
    remix.

### What the user actually designs

“User-designed” does not falsely mean the user manually drew every trace or
wrote every RTL line. It means the design originated from their request, their
material choices governed it, and they can inspect, reject, revise, own, and
remix the resulting editable sources. Attribution remains granular:

- **User-authored:** intent, use case, vocabulary and behavior, constraints,
  budget, purchased-input policy, interface/form-factor choices, contributed
  recordings or sketches, and every explicit approval.
- **Daemon-generated under user direction:** candidate architecture, training
  recipe, new model weights, accelerator logic, SoC configuration, carrier PCB,
  firmware, fixtures, tests, and documentation that the user accepts.
- **Upstream-authored and reused:** RISC-V ISA/core, LiteX, CFU-Playground,
  EDA/toolchain software, licensed datasets, reference circuits, and component
  models.
- **Vendor/executor-produced:** FPGA silicon/module, electronic components,
  fabricated/assembled PCB, and specialist measurements or labor.

The public claim must state all four categories. The user is the project
originator and decision author; daemon, upstream, and executor contributions
retain their own credit and licenses.

### Remixable design units

| Unit | Editable content | A later user can remix... |
|---|---|---|
| System Branch | Goal template, component graph, budgets, gates | the entire recipe for a new device |
| Behavior | words, labels, LED/GPIO actions, thresholds | what the same hardware does |
| Model | data manifest, training recipe, weights, quantization | language, speakers, noise, or accuracy |
| Accelerator | operator contract, RTL/Amaranth, registers, tests | speed/area/power trade-offs |
| SoC/gateware | RISC-V core configuration, buses, memory map, bitstream build | FPGA/module or peripheral mix |
| Carrier board | schematic, layout, BOM, connectors, microphone, fabrication files | form factor, parts, or interfaces |
| Firmware | boot, drivers, inference application, update path | runtime behavior and peripherals |
| Mechanical | enclosure and fixtures | housing and assembly method |
| Evaluator/evidence | golden vectors, HIL procedures, measurements | stronger tests without changing candidates |

Each unit carries a machine-readable manifest with stable identity, semantic
version, license, authors/contributors, upstream Branches, input/output
interfaces, compatibility constraints, reproducible build command, tests, and
physical evidence level. A remix creates a new descendant Branch; it never
silently overwrites its ancestor.

Compounding is demonstrated when a second user discovers the released design
through their chatbot, changes one meaningful requirement, reuses every
compatible unit, rebuilds only the affected dependency cone, and contributes a
passing descendant back to the commons. Proof v0's reference remix changes the
vocabulary and output behavior, retrains/requantizes the model, updates
firmware, reuses the original board/SoC/accelerator unchanged, and passes on
physical hardware.

### Current platform contradiction and prerequisite

Freshness check on 2026-07-15 found:

- `PLAN.md` and `docs/design-notes/2026-04-15-node-software-capabilities.md`
  specify `required_capabilities`, capability handlers, and an
  `external_tool_node` seam.
- Current `workflow/branches.py::NodeDefinition` exposes source-code and
  prompt-template execution but no `required_capabilities` or external-tool
  node kind.

Therefore the hardware project can be specified and developed as an ordinary
user repository now, but the final claim that a TinyAssets daemon executed the
physical loop is blocked on the **generic** external-tool capability substrate.
The fix must close that generic PLAN/code gap; this project must not add a
hardware-only execution bypass.

## Technical Stack

The implementation plan must pin exact releases or commit identifiers in a
checked-in lock/receipt before the first reproducible build.

| Surface | Selected family | Purpose |
|---|---|---|
| ISA | ratified RISC-V RV32 profile supported by chosen soft core | portable CPU contract |
| SoC | LiteX + compatible RISC-V soft CPU | CPU, bus, memory, UART, timers |
| Accelerator reference | CFU-Playground | CPU/CFU integration, profiling, TFLM flow |
| RTL/gateware | Verilog and/or Amaranth | custom function unit and integration |
| Simulation | Verilator + Renode co-simulation where supported | deterministic software/gateware proof |
| FPGA synthesis/P&R | Yosys + nextpnr + ECP5 bitstream tooling | open bitstream build |
| Firmware | C/C++ with RISC-V GCC; TensorFlow Lite Micro-compatible inference | boot and inference runtime |
| Model | Python training stack; integer-quantized export | reproducible keyword spotter |
| PCB | KiCad | schematic, layout, BOM, Gerber, placement, 3D exports |
| User control plane | supported chatbot UI + live TinyAssets connector | conversational Goal/Branch creation, steering, approval, and remix |
| Build orchestration | TinyAssets daemons + Make + pinned container/WSL environment | asynchronous execution and one-command reproduction |
| Evidence | JSON/JSONL, CSV, logs, photos/video, instrument captures | gate inputs and audit trail |

## Command Contract

These commands are the required repository interface. The implementation plan
may change internals, but not remove these outcomes without updating the spec.

```bash
# Reproducible environment and source/license inventory
docker compose build --pull toolchain
docker compose run --rm toolchain make doctor
docker compose run --rm toolchain make licenses

# Model: train/fine-tune, evaluate, quantize, lock golden vectors
docker compose run --rm toolchain make model-train SEED=20260715
docker compose run --rm toolchain make model-eval SPLIT=held-out
docker compose run --rm toolchain make model-export FORMAT=int8
docker compose run --rm toolchain make golden-vectors

# CPU baseline, accelerator tests, co-simulation, synthesis
docker compose run --rm toolchain make firmware-baseline TARGET=proof_v0
docker compose run --rm toolchain make rtl-test
docker compose run --rm toolchain make cosim TARGET=proof_v0
docker compose run --rm toolchain make gateware TARGET=proof_v0
docker compose run --rm toolchain make timing TARGET=proof_v0

# PCB checks and manufacturing package
docker compose run --rm toolchain make pcb-erc
docker compose run --rm toolchain make pcb-drc
docker compose run --rm toolchain make pcb-fab-package REV=A

# Aggregate pre-purchase gate
docker compose run --rm toolchain make preflight TARGET=proof_v0 REV=A

# Hardware-in-loop; Windows example shown, Linux uses /dev/tty*.
python tools/hil_test.py --port COM5 --cold-boots 10 --inferences 1000 \
  --golden evidence/golden-vectors.jsonl --output evidence/hil-run.json

# Connector, authorship, lineage, and downstream-remix receipts
python tools/verify_conversation.py \
  --receipt evidence/conversations/origin-build.json \
  --require-live-connector --require-user-decisions --require-physical-link
python tools/verify_lineage.py --manifest design.yaml \
  --require-attribution --require-physical-remix

# Final evidence verification; fails if any physical artifact is missing.
python tools/verify_release.py --manifest evidence/release-manifest.yaml \
  --require-board-rev A --require-physical --require-conversation \
  --require-descendant-remix
```

No command may silently substitute host/cloud inference for FPGA inference.

## Project Structure

The separate user repository should begin with this bounded shape:

```text
design.yaml                 Root design-unit graph, compatibility, lineage
branch/                     TinyAssets Goal/Branch definition and node contracts
behavior/                   Vocabulary, output mapping, thresholds, behavior card
hardware/
  gateware/                 SoC integration, CFU RTL/Amaranth, constraints
  pcb/                      KiCad source, libraries, fabrication exports
  mechanical/               Enclosure and fixture source
firmware/                   Boot, drivers, TFLM application, serial receipt
model/                      Training, quantization, evaluation, model card
tools/                      HIL, evidence, lineage, conversation verifiers
tests/
  model/                    Accuracy and quantization tests
  rtl/                      Unit/property tests and golden vectors
  integration/              Renode/Verilator and firmware tests
  hardware/                 HIL scenarios and fixtures
  remix/                    Dependency-cone and descendant compatibility tests
evidence/
  conversations/            Private/redacted connector receipts and approvals
  lineage/                  Ancestor/descendant and attribution receipts
  physical/                 Raw logs, measurements, photos/video index
vendor/                     Pinned upstream manifests only; no copied mystery IP
Dockerfile                  Reproducible toolchain image
compose.yaml                Host/container boundary
Makefile                    Required command contract
README.md                   Chatbot build, reproduce, and remix path
LICENSES.md                 Source, model, data, hardware license inventory
```

## Code and Artifact Style

- Identifiers use functional names: `keyword_cfu`, `inference_cycles`,
  `model_sha256`; avoid marketing names in interfaces.
- Every generated binary is traceable to source hashes and a command receipt.
- Every design unit declares authorship separately from ownership, approval,
  fabrication, and upstream lineage.
- Hardware registers and serial receipts use explicit-width integers and
  versioned schemas.
- Generated Gerbers, bitstreams, models, and binaries are release artifacts,
  never the only editable source.
- No hidden notebook state. Training notebooks may explain, but scripts own
  reproducible execution.

Minimum design-unit manifest shape:

```yaml
schema: tinyassets.design-unit.v1
design_id: voice-node/model/en-us-command-v1
kind: model
version: 1.0.0
license: Apache-2.0
originating_user: user-ref-or-private-hash
generated_by: daemon-run-ref
upstreams:
  - design_id: tensorflow/speech-commands
    version: pinned-manifest-hash
interfaces:
  input: audio.pcm16.16000.mono.v1
  output: command-scores.int8.v1
compatible_with:
  firmware_abi: voice-node.inference.v1
build: make model-export FORMAT=int8
tests: make model-eval
evidence_level: physically-tested
```

Example serial receipt:

```json
{
  "schema": "proof.inference.v1",
  "board_rev": "A",
  "gateware_sha256": "<64 hex chars>",
  "firmware_sha256": "<64 hex chars>",
  "model_sha256": "<64 hex chars>",
  "class_id": 3,
  "score_q15": 28741,
  "cycles": 18422,
  "accelerator": "keyword_cfu"
}
```

## Testing Strategy

### Connector and conversational-build gates

- A real user starts from a new conversation in a rendered supported chatbot
  with the live TinyAssets connector installed.
- The connector creates or binds the Goal and initial Branch; the user is not
  required to edit the repository or operate a developer CLI.
- The receipt proves that behavior, hardware boundary, budget, purchased-input
  policy, and acceptance gates were chosen or explicitly accepted in chat.
- Every irreversible action, paid order, and physical-machine action links to a
  prior user approval in the same durable Goal.
- Branch revisions, daemon actions, failures, and physical evidence are
  retrievable and understandable from the chatbot surface.
- Public evidence may use redacted text and stable hashes; it must prove the
  conversation/action chain without exposing private transcript content.

### Attribution and remix gates

- Every unit distinguishes originating-user decisions, daemon-generated work,
  upstream sources, and vendor/executor production.
- Licenses and compatibility declarations permit the advertised downstream
  reuse; an incompatible or non-redistributable unit cannot be published as
  openly remixable.
- An independent second user discovers the passing ancestor through their
  chatbot and creates a descendant Branch through the connector.
- The descendant changes vocabulary and output mapping, rebuilds the behavior,
  model, and firmware dependency cone, and reuses the original accelerator,
  SoC, and carrier-board units without copying or losing lineage.
- The descendant runs on physical hardware and passes its locked model,
  firmware, and live-input gates. A design-file-only fork does not satisfy the
  compounding proof.

### Model gates

- Deterministic training receipt records code, data manifest, seed, parameters,
  compute type, and resulting model hash.
- Held-out integer-model accuracy is at least 85% on the frozen initial command
  subset and no more than 2 percentage points below the floating baseline.
- The personal/live-use set is reported separately and never substituted for
  the held-out set.

### Gateware and firmware gates

- CFU unit tests cover arithmetic saturation, signedness, reset, invalid opcode,
  boundary tensor shapes, and repeat invocation.
- CPU-only and accelerated paths match every golden vector under the declared
  integer tolerance.
- Co-simulation completes the boot and 100 inference sequence before synthesis.
- Place-and-route meets the declared clock with no unconstrained paths.
- Resource utilization leaves at least 10% headroom in each load-bearing FPGA
  resource class unless the evaluator records a host-approved exception.

### PCB gates

- ERC and DRC return no unexplained errors.
- The manufacturing packet contains Gerbers, drills, BOM, pick-and-place,
  schematic PDF, board render, board revision, and source hash.
- Before module insertion, power rails, shorts, polarity, USB protection, and
  test points pass a rail-first checklist.
- Final acceptance uses hardware matching released fabrication files. Any bodge
  wire or component substitution requires a committed engineering-change record
  and a regenerated release manifest; an undocumented bodge fails the gate.

### Physical acceptance gates

- Ten consecutive cold boots after at least 10 seconds unpowered.
- One thousand locked-vector inferences with zero unexplained mismatches.
- Median accelerated inference is at least 2x faster than CPU-only inference on
  the same FPGA SoC and model.
- At least 20 live microphone trials across at least two speakers are recorded;
  results are reported without replacing the held-out accuracy gate.
- Board current, critical rail voltages, and device temperature stay within
  component limits for a continuous 30-minute workload.
- The released device completes inference with the host network disconnected.

## Boundaries

### Always

- Begin and steer the project through the live connector and keep its durable
  Goal resumable from the chatbot surface.
- Present material design alternatives in user language and record which
  option the user chose or accepted.
- Keep the generator, evaluator, and physical evidence recorder separate.
- Lock golden vectors before optimizing the accelerator.
- Dry-run every machine action and procurement packet before authorization.
- Preserve raw tool, vendor, serial, and instrument outputs.
- Record purchased inputs and specialist contributions with provenance.
- Preserve unit-level lineage, attribution, licenses, compatibility, and
  evidence when publishing or remixing.
- Use a reversible FPGA step before any ASIC or local-fab commitment.

### Ask first

- Any purchase, PCB order, assembly order, or paid specialist engagement.
- Selecting the exact FPGA module or changing its connector/power contract.
- Adding a proprietary tool, IP block, model weight, or dataset.
- Changing the command vocabulary, accuracy floor, clock, voltage, or thermal
  envelope after evidence collection begins.
- Moving from carrier PCB to raw-FPGA custom board.
- Any TinyAssets platform-code change needed to execute the Branch.
- Publishing raw conversation text, personal recordings, user identity, or
  private design inputs rather than a redacted receipt.
- Changing the ownership, licensing, credit, or compensation terms of a design
  unit or its descendant.

### Never

- Never claim physical success from simulation, renderings, or vendor receipts.
- Never count a developer-prepared repository plus a final chatbot summary as a
  chatbot-built device.
- Never claim the user manually authored daemon-generated, upstream, or
  vendor-produced work; preserve the contribution ledger.
- Never handle mains voltage, cells/batteries, lasers, vacuum, hazardous
  chemicals, or semiconductor process steps in proof v0.
- Never allow a candidate-generating daemon to edit locked evaluators or golden
  vectors during an optimization run.
- Never hide purchased modules or cloud/host computation behind a
  "self-manufactured" claim.
- Never add an FPGA-, KiCad-, or model-specific MCP primitive to TinyAssets.
- Never flash or power unknown hardware without rail-first checks and explicit
  user authority.

## Success Criteria

Proof v0 is complete only when all conditions are true:

1. The user approves this spec, the technical plan, and the task breakdown.
2. Opposite-provider research review returns approve/adapt and every required
   adaptation is incorporated.
3. A real user starts from a new rendered-chatbot conversation, and the live
   connector creates/binds and steers the durable Goal and initial Branch
   without requiring the user to edit source or operate a developer CLI.
4. Conversation receipts prove the user's material decisions, approvals,
   Branch revisions, daemon actions, failures, and physical-evidence links.
5. The Branch is an ordinary TinyAssets design graph whose versioned units are
   independently discoverable and remixable.
6. The separate source repository reproduces model, firmware, gateware, and PCB
   checks from documented commands on a clean environment.
7. A custom carrier PCB matching released source is physically manufactured.
8. The board passes the cold-boot, inference, acceleration, live-input, thermal,
   and offline gates above.
9. Evidence includes raw logs, hashes, measurement captures, photographs/video
   index, purchased-input ledger, failures, and repairs.
10. An independent evaluator verifies the evidence manifest without consulting
   the generator's narrative.
11. An independent second user discovers the ancestor through their chatbot,
   changes its vocabulary/behavior, receives a lineage-preserving descendant,
   and runs that remix successfully on physical hardware.
12. The original and descendant Branches each identify what the user decided,
   what daemons generated, what upstreams supplied, and what vendors built.
13. Post-fix/acceptance monitoring either shows clean real-user use or leaves an
    explicit watch item rather than claiming adoption.

## Not in Proof v0

- A custom ASIC, Tiny Tapeout submission, or locally fabricated transistor.
- A raw-FPGA motherboard, Linux desktop, GPU, PCIe card, or high-speed DDR
  layout.
- A general-purpose consumer computer or conversational AI device; proof v0 is
  a small offline voice-command/control module.
- An LLM running on the FPGA; keyword spotting is the bounded trained-model
  workload.
- Battery operation, wireless radios, camera input, display, enclosure polish,
  regulatory certification, or volume production.
- Autonomous purchasing or hazardous machine operation.
- General hardware functionality added to TinyAssets core.

## Open Questions for Host Review

1. Does “a conversation to count” mean one durable Goal that may be resumed
   across multiple chatbot sessions, as specified here, or literally one
   uninterrupted chat window? The recommended default is the durable Goal.
2. Is a replaceable ECP5-class module on a genuinely custom carrier strong
   enough for proof v0, with raw-FPGA PCB integration deliberately moved to v1?
3. Is the offline voice-command module the right first useful workload, or
   should the same architecture target another user-chosen physical behavior?
4. Is the 2x same-device speedup gate ambitious enough to make the accelerator
   undeniable without turning proof v0 into a benchmark project?
5. Should live acceptance require the spoken wake word "Tiny", which would add
   a custom-data collection/fine-tuning task, or use existing licensed command
   classes first?
6. What maximum pre-approved budget, if any, may the Branch spend during
   planning and prototype procurement? The default remains zero.

## Primary References

- RISC-V ratified specifications: <https://docs.riscv.org/reference/home/index.html>
- LiteX: <https://github.com/enjoy-digital/litex>
- YosysHQ nextpnr: <https://github.com/YosysHQ/nextpnr>
- CFU-Playground documentation: <https://cfu-playground.readthedocs.io/en/latest/>
- CFU-Playground paper: <https://arxiv.org/abs/2201.01863>
- TensorFlow Speech Commands dataset: <https://www.tensorflow.org/datasets/catalog/speech_commands>
- KiCad CLI documentation: <https://docs.kicad.org/master/en/cli/cli.html>
- TinyAssets capability design: `docs/design-notes/2026-04-15-node-software-capabilities.md`
- Approved idea: `ideas/2026-07-15-democratized-compute-stack.md`
