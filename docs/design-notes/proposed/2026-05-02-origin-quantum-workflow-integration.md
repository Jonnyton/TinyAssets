# Origin Quantum As Optional Workflow Compute

Date: 2026-05-02
Status: proposed direction, not implementation-approved

## Summary

Origin Quantum should not become a core Workflow dependency. The strongest
path is to treat Origin Quantum access as an optional, capability-gated
executor backend for quantum experiments and quantum-informed evaluators.

The useful frame is:

```text
chatbot autoresearch request
  -> OptimizationRun
  -> capacity_grant_ref
  -> executor_backend=origin_quantum_cloud or local_quantum_sim
  -> QuantumTask artifacts
  -> EvalResult evidence/artifacts/cost/freshness
  -> conservative merge or human review
```

This aligns with:

- `workflow/evaluation/schema.py` as the canonical `EvalResult` shape.
- `docs/design-notes/2026-05-02-community-evolvable-optimization-integration.md`.
- `.claude/agent-memory/navigator/2026-05-02-optimizationrun-rule1-prereview.md`.
- `.claude/agent-memory/navigator/project_hostless_byok_alpha.md`.

## Current Origin Quantum Facts

Research freshness: 2026-05-02, checked against current Origin Quantum and
OriginQ Cloud documentation.

Origin Quantum currently exposes:

- Origin Wukong, described by Origin Quantum as a superconducting quantum
  computer with a 102-bit independently developed superconducting chip and
  cloud access.
- QPanda3 / pyqpanda3, a Python SDK for circuit construction, CPU/GPU
  simulation, noise modeling, variational algorithms, transpilation, and cloud
  execution.
- `pyqpanda3.qcloud.QCloudService`, which authenticates with an API key, lists
  backends, submits async jobs, checks status, and retrieves counts,
  probabilities, raw data, and expectation values.
- Origin Pilot / Origin Sinan operating-system layer claims around
  multi-backend scheduling, queueing, hybrid quantum-classical task management,
  monitoring, and noise correction.

External sources used:

- Origin Wukong product page:
  `https://originqc.com/quantum-machines/quantum-computer`
- QPanda3 product page:
  `https://originqc.com/developer-tools/qpanda`
- pyqpanda3 getting started:
  `https://qcloud.originqc.com.cn/document/pyqpanda3-docs/en/tutorial/getting-started`
- pyqpanda3 cloud computing:
  `https://qcloud.originqc.com.cn/document/pyqpanda3-docs/en/tutorial/cloud-computing`
- Origin Pilot download note:
  `https://originqc.com/blogs/origin-pilot-download`
- Origin NISQ 2026 note:
  `https://originqc.com/blogs/nisq-era-status-2026`

Important caveat: Origin's cloud docs name real QPU access around
`origin_wukong` / 72+ qubits while the product page markets a 102-bit chip and
customizable systems beyond 100 qubits. Workflow should not hard-code qubit
claims. It should discover live backend metadata at runtime and persist what
the provider reports for that job.

## Why This Matters To Workflow

Workflow is becoming an evaluation-driven optimization substrate, not just a
fantasy daemon. Origin Quantum is relevant because it stress-tests the exact
interfaces that the ASI-Evolve slice and capacity-grant work are defining:

1. External compute is stochastic and evidence-heavy.
2. Jobs are asynchronous and queue-bound.
3. Credentials and spend must be grant-scoped.
4. Results must be reproducible enough to inspect later.
5. Classical baselines remain mandatory.

That makes quantum a good architecture test for Workflow's outer loop. It does
not make quantum a good near-term way to "make the daemon smarter."

## Fit Against Current Project Threads

### EvalResult / Evaluation Layers

`workflow/evaluation/schema.py` already has the fields a quantum backend needs:

- `score`: normalized usefulness score, usually derived from comparison against
  a classical baseline.
- `verdict`: `pass`, `fail`, `skip`, or `error`.
- `kind`: likely `numeric` or `custom`.
- `evidence`: backend metadata, shots, counts, probabilities, expectation
  values, calibration snapshot, and baseline comparison.
- `artifacts`: circuit source, QASM/OriginIR if available, job receipt,
  provider raw payload, and plotted result distributions.
- `cost`: credits, estimate, queue wait, shot count, and billed units if known.
- `ran_at` / `freshness`: calibration date, result timestamp, and backend
  availability snapshot.

No new evaluator primitive is needed. A quantum evaluator is just another
structural-subtyping evaluator that returns `EvalResult`.

### OptimizationRun

The OptimizationRun pre-review says budget should be `capacity_grant_ref`, not
raw cents/tokens/concurrency on the optimization run itself. Origin Quantum
reinforces that. A quantum run has provider credentials, credits, queues,
quota, and policy. Those belong under Capacity Grant and Budget Reservation.

Suggested OptimizationRun fields relevant to quantum:

```text
target_kind = "node" | "branch" | "evaluator" | "experiment"
search_policy = "grid" | "random" | "qaoa" | "vqe" | "quantum_sampler"
capacity_grant_ref = "grant:..."
executor_backend = "local_quantum_sim" | "origin_quantum_cloud"
evaluator_chain_ref = "classical_baseline_then_quantum_compare"
editable_surface = typed circuit/spec params, not arbitrary code
merge_policy = human-review by default
```

Do not add a separate `QuantumRun` top-level primitive unless the field set
cannot be represented as an OptimizationRun child activation plus artifacts.

### Capacity Grant / Executor Backend

Origin Quantum access is a textbook Executor Backend:

- `origin_quantum_cloud`: remote provider access through official API key.
- `local_quantum_sim`: local pyqpanda3 simulator, no provider credential.
- future `third_party_host`: another host contributes quantum credentials or
  simulator capacity.

The API key must be treated like any other credential:

- stored behind Credential Broker,
- referenced by Capacity Grant,
- checked before job submission and before result ingestion,
- bounded by spend/shot/queue limits,
- revoked cleanly,
- never committed or echoed into public artifacts.

Origin Quantum outputs can be public only when the input is public or explicitly
redacted. Private uploaded data cannot silently become public reusable
quantum-training examples.

### Node Autoresearch

The best user-facing word remains "autoresearch." Quantum should appear as an
optional backend selected by the platform, not a term the user must understand.

Example user request:

> improve this routing evaluator overnight under $15; try classical local
> search first, then run a small quantum sampler if it is still ambiguous; ask
> before merging.

The chatbot should translate that into:

- classical baseline run,
- simulator proof,
- optional Origin Quantum execution if a grant exists,
- evidence-rich comparison table,
- no automatic merge unless policy says so.

### Priya / Scientific Domain

Priya's MaxEnt sensitivity sweep is not a quantum-first use case. For her, the
right first milestone remains normal scientific autoresearch: 210 fits,
numeric evaluator, reproducibility artifact, cost estimate.

Quantum becomes interesting later for:

- quantum-kernel experiments on ecological feature maps,
- QUBO-style model-selection or subset-selection demos,
- teaching/demonstration notebooks that show Workflow can orchestrate exotic
  compute while keeping classical baselines honest.

Do not force quantum into Priya's first happy path. It would add novelty tax
without increasing her chance of paper acceptance.

## Next-Level Product Concept

### Quantum Capability Pack

Ship this as a domain/capability pack, not platform core:

```text
workflow[quantum]
  workflow/quantum/
    providers/originq.py
    providers/local_pyqpanda.py
    circuits.py
    results.py
    evaluators.py
    tasks.py
  tests/test_quantum_*.py
  docs/examples/quantum/
```

The default install stays clean for tier-3 OSS contributors. Missing
`pyqpanda3` returns a `skip` `EvalResult` with an install hint, following the
existing optional-dependency pattern used by scientific evaluators.

### QuantumTask Contract

Keep the first contract small:

```text
QuantumTask
  task_id
  backend_ref
  circuit_ref
  algorithm_kind
  shots
  options
  submitted_job_id
  status
  result_ref
  baseline_ref
  capacity_grant_ref
```

This can initially live as an artifact schema inside OptimizationRun rather
than a database table. Promote it only if multiple features need indexed
querying by quantum job id, backend, or result.

### QuantumEvalResult Mapping

Quantum evaluators return ordinary `EvalResult`:

```text
EvalResult(
  score=<baseline-relative score>,
  verdict="pass" | "fail" | "skip" | "error",
  kind="numeric",
  label="quantum_backend_compare",
  evidence={
    "backend": "origin_wukong",
    "shots": 3000,
    "counts": {...},
    "probabilities": {...},
    "classical_baseline": {...},
    "calibration": {...},
  },
  artifacts={
    "circuit": "artifact:...",
    "provider_raw": "artifact:...",
    "plot": "artifact:...",
  },
  cost={
    "provider": "origin_quantum",
    "credits_estimated": ...,
    "queue_wait_seconds": ...,
  },
  freshness={
    "backend_status_checked_at": "...",
    "calibration_observed_at": "...",
  },
)
```

### First Demo Worth Building

Build "quantum-backed branch/evaluator selection" rather than a chemistry demo.

Reason:

- It uses Workflow-native objects.
- It can run entirely on simulators first.
- It creates a clear classical baseline.
- It exercises OptimizationRun, EvalResult, artifacts, and capacity grants.

MVP:

1. Take a tiny candidate-selection problem:
   - choose K candidate nodes/branches under cost and diversity constraints, or
   - solve small Max-Cut / graph partitioning over branch similarity.
2. Encode as QUBO.
3. Run classical brute force or heuristic baseline.
4. Run pyqpanda3 local simulator.
5. If `QPANDA3_API_KEY` grant exists, submit to Origin Quantum cloud backend.
6. Compare distributions and persist as `EvalResult`.
7. Display "quantum did/did not beat baseline" in chatbot-readable evidence.

Success is not "quantum wins." Success is "Workflow can safely orchestrate a
non-LLM, credentialed, stochastic external compute backend and produce
inspectable evidence."

## Implementation Slices

### Slice Q0: Research And Contract Freeze

- Create a tiny design spec for `QuantumTask` artifact schema.
- Define allowed backend ids: `local_pyqpanda_cpu`, `local_pyqpanda_gpu`,
  `origin_quantum_cloud`.
- Define the `EvalResult` mapping.
- Define privacy defaults: circuit public only if inputs are public; raw
  provider payload private-by-default.

Exit proof: no runtime dependency, docs only, reviewed against OptimizationRun
Rule-1 atomization.

### Slice Q1: Local Simulator Evaluator

- Add optional dependency group `quantum = ["pyqpanda3>=0.3.5"]` if install
  proves clean on Windows/Linux/macOS.
- Add lazy loader `_load_pyqpanda3_backend()`.
- Implement `LocalQuantumCircuitEvaluator`.
- Return `skip` if dependency is missing.
- Test with a Bell-state or tiny Max-Cut circuit.

Exit proof: no network, deterministic tests, clean default install.

### Slice Q2: Artifact Bridge

- Persist circuit text, options, counts, and baseline comparison as artifacts.
- Populate `EvalResult.evidence`, `artifacts`, `cost`, `ran_at`, and
  `freshness`.
- Ensure no credentials or private input values are stored in public artifacts.

Exit proof: serialized result round-trips through current evaluator consumers.

### Slice Q3: Origin Quantum Cloud Adapter

- Add `OriginQuantumCloudBackend` behind official API credentials only.
- Require `capacity_grant_ref`.
- Use `QCloudService.backends()` as startup/job-time probe.
- Submit async job, store provider job id, poll status, ingest final result.
- Fail loudly on missing dependency, missing grant, unavailable backend, or
  provider error.

Exit proof: can be tested with a fake `QCloudService`; real QPU test stays
manual/integration-gated until a grant exists.

### Slice Q4: Autoresearch Integration

- Allow OptimizationRun search policies to select `quantum_sampler` only when
  a simulator proof exists and a quantum capacity grant is active.
- Keep merge policy human-review by default.
- Add chatbot copy that says "try quantum backend" only as an advanced option.

Exit proof: one end-to-end demo from natural-language request to evidence table
without touching public uptime surfaces.

### Slice Q5: Community Capability Pack

- Publish a small example pack: "Quantum candidate selection."
- Include classical baseline, simulator result, optional Origin Quantum path,
  and reproducibility artifact.
- Let community users remix the pack without requiring Origin credentials.

Exit proof: clean-clone user can run simulator demo; credentialed user can swap
in Origin Quantum without code changes.

## Risks And Guardrails

1. Novelty tax: quantum can distract from uptime and directory acceptance.
   Keep all work post-uptime and optional.
2. False claims: no "quantum advantage" language unless a baseline comparison
   proves it for that exact task.
3. Credential leakage: API key only through capacity grant / credential broker.
4. Data residency: no sensitive or private user uploads to Origin Quantum by
   default.
5. Stochastic drift: store shots, backend metadata, calibration time, and raw
   distributions.
6. Queue latency: cloud QPU jobs are async activations, never blocking chatbot
   request handlers.
7. Dependency blast radius: pyqpanda3 is optional and lazy-loaded.
8. Provider metadata drift: discover live backend capabilities; do not hard-code
   qubit counts.
9. Evaluation gaming: candidate generators cannot edit the evaluator or circuit
   baseline used to judge them.
10. Compliance/geopolitical risk: Origin Quantum is China-based; enterprise or
    sensitive workloads need explicit policy before use.

## Open Questions

1. Should `QuantumTask` stay artifact-only for the first demo, or does job
   polling require a table immediately?
2. What is the first safe public demo: branch selection, evaluator selection,
   Max-Cut over node graph, or a small chemistry/VQE example?
3. Do we want an `ExecutorBackend` enum value for quantum generally, or just
   backend-specific capability labels under capacity grants?
4. Should Origin Quantum credentials be user-BYOK only, or can a future
   platform_pool grant subsidize limited public demos?
5. What privacy label should apply to provider raw payloads by default:
   private-to-user or private-to-branch?

## Recommendation

Promote the Origin Quantum idea as a post-uptime, optional capability pack that
validates Workflow's evaluation and capacity-grant architecture. The next build
step should be a simulator-only `EvalResult` proof, not cloud QPU access.

Origin Quantum should be useful because Workflow can ask better questions of
quantum compute, not because quantum compute replaces Workflow's core engine.
