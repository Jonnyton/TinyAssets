---
id: markovic-fingerprint-rd-scaling-program
title: "Markovic Fingerprint RD Scaling Program — Five-Stage Plan"
type: research_program
created: 2026-05-05
updated: 2026-05-05
goal_id: cbc96a78d7ff
status: planning
tags: [research-program, simulation, reaction-diffusion, fingerprint, turing, glover-2023, sim-only]
sources:
  - https://www.cell.com/cell/fulltext/S0092-8674(23)00045-4
  - https://www.science.org/doi/10.1126/science.1252960
---

# Markovic Fingerprint RD Scaling Program

Goal anchor: **`cbc96a78d7ff`** — *Markovic fingerprint RD scaling program*.

This is the planning record for a computational-systems-biology research program. It is **not** an executable workflow; it is the durable platform-side analogue of a lab notebook program plan. Local execution stays local; the platform records provenance, milestones, and gate state.

## Research question

Do the published Glover et al. (2023, *Cell*) EDAR–WNT–BMP modified Gierer–Meinhardt parameters quantitatively predict the empirically observed scaling of total fingerprint ridge count across digits of different size within an individual hand, without digit-specific parameter tuning?

## Current state (2026-05-05)

- Validation gates 001–003 closed.
- Gate 004 lightweight masked-domain prototype REJECTED 0/5 seeds. Rejection record preserved verbatim.
- B2 decomposed into Validation 004 ladder (V004-A through V004-D). Local spec: `validation/04_fv_solver_requirements.md`.
- **V004-A: ACCEPTED.** Max growth-rate rel error 4.71×10⁻³ vs <10⁻² bar.
- **V004-B: RUNNING (full mode, in-progress).** Local pid 26544 started 2026-05-04T20:01:53.6749900-07:00; last heartbeat ≈ 2026-05-05T00:32:01-07:00; ~4.4 h CPU consumed; final JSON not yet present; stderr empty. **No V004-B scientific result exists until `validation/04_fv_nonlinear_wavelength_full.json` is on disk.** See V004-B entry below for the in-progress run manifest discipline.
- Platform execution remains **no-go** pending SOP-RXD-001 clearance.

## Gate 004 result and decision (2026-05-05) — REJECTION RECORD, DO NOT REINTERPRET

**File**: `gates/04_masked_digit_prototype.py` (local; not platform-attested — see [[PR-017]]).

**Method**: lightweight masked-domain prototype using nearest-active-cell mask extension with semi-implicit spectral diffusion on the bounding box. Imports canonical `kinetics.py`. Geometry: width 96, total length 192, rectangle + half-disk cap radius 48. `dt=0.2`, `steps=6000`. Five RNG seeds 2026050400…404, `noise_scale=1e-4`. Explicitly documented as not manuscript-grade FV/FEM.

**Acceptance metric (predeclared)**: in the 1–2 wavelength annulus inside the distal cap, median angle between activator wavevector and local boundary tangent in [70°, 110°] for ≥4/5 seeds.

**Result**: 0 / 5 accepted.

| Seed | Median angle (1–2λ annulus) |
|---|---|
| 2026050400 | 37.858° |
| 2026050401 | 37.748° |
| 2026050402 | 37.865° |
| 2026050403 | 37.710° |
| 2026050404 | 37.825° |

**Diagnostic (seed 2026050400)**: in the 0–0.5λ near-boundary annulus, wavevector median 63.37° (ridge-tangent median 26.63° off boundary tangent); in the predeclared 1–2λ annulus, wavevector median 37.86° (ridge-tangent median 52.14°). Not a simple complement-angle bug.

**Interpretation**: prototype rejection, not biological falsification.

**Local notes**: `notes/gate004_masked_digit_prototype.md`, `notes/gate004_orientation_diagnostic.md`, `notes/platform_gate004_update_2026-05-04.md`.

## Validation 004 ladder

B2 is decomposed into four stages. Local spec: `validation/04_fv_solver_requirements.md`. The methods change is the **solver**, not the bar; V004-D acceptance rule, seed list, and geometry are unchanged from the rejected prototype to preserve direct comparability.

### V004-A — Rectangular linear-mode validation for the new FV diffusion operator

**Status (2026-05-05): ACCEPTED.**

**Implementation**: `solvers/masked_fv.py` — cell-centered masked finite-volume, explicit canonical reaction (from `kinetics.py`), implicit diffusion via NumPy conjugate gradient, zero flux across inactive/out-of-domain faces. Periodic rectangular mode available for validation. Treated as validated only for rectangular linear modes; **not** yet validated for masked digit biology.

**Harness**: `validation/04_fv_modal_growth_validation.py` — exact discrete finite-volume Fourier eigenvalues on a full rectangular periodic mask.

**Configuration**:
- domain L = 384, n = 384, dx = 1
- dt = 0.05, t_final = 4.0
- modes tested: 17, 19, 21, 23, 25

**Result**:
- max measured-vs-semidiscrete growth-rate relative error: **4.71×10⁻³** (acceptance bar: <10⁻²)
- max update-map relative error: 8.09×10⁻⁵ (machine-precision level)
- all conjugate-gradient diffusion solves converged
- mode 21: measured growth 0.05672608, semidiscrete growth 0.05680486

**Methods note for downstream gates**: V004-A validated at dt = 0.05. Original Gate 004 prototype used dt = 0.2. V004-D will inherit the dt revision while keeping seeds, geometry, and acceptance rule unchanged.

**Local artifacts**: `validation/04_fv_modal_growth.csv`, `validation/04_fv_modal_growth_report.md`, `validation/04_fv_solver_requirements.md`.

**Severity rule**: V004-A is a hard gate. Pass means the new solver is a candidate for V004-B; it does **not** yet mean it is a candidate for V004-D.

### V004-B — Nonlinear rectangular wavelength check

**Status (2026-05-05): RUNNING (full mode, in-progress; not accepted, not rejected).**

**No V004-B scientific result exists until `validation/04_fv_nonlinear_wavelength_full.json` is on disk.** Any pre-saturation FFT value is non-result, including any value the running process has logged to stdout. README.md and `notes/long_running_simulation_sop.md` enforce this discipline locally; this page enforces it on the platform side.

**In-progress run manifest (heartbeat as of 2026-05-05T00:32:01-07:00)**:
- pid: 26544
- started_at: 2026-05-04T20:01:53.6749900-07:00
- last_checked: 2026-05-05T00:32:01-07:00
- process_running: true
- responding: true
- cpu_seconds_consumed: ≈15991
- final_outputs_present: false (waiting on `validation/04_fv_nonlinear_wavelength_full.json`)
- stdout/stderr tail: empty (no error output)
- termination_reason: not yet (still running)
- harness: `validation/04_fv_nonlinear_wavelength_check.py --mode full`
- locked controls: `saturation_delta_threshold=1e-6`, `saturation_window=1000`, `cg_iteration_ceiling=200`, `max_steps=100000`
- run-manifest file: `validation/04_fv_nonlinear_wavelength_full_run_manifest.json`
- heartbeat tool: `tools/check_v004b_full_run.ps1`
- heartbeat SOP: `notes/long_running_simulation_sop.md`

**Heartbeat is read-only and does not touch the running solver process.** The check is local OS introspection (process state, file existence, stderr tail), not signaling into the run. The running process is **not** to be interrupted to query progress. The fact that this discipline lives entirely off-platform is exactly the gap [[PR-030]] is filed against.

**Harness**: `validation/04_fv_nonlinear_wavelength_check.py`. Defaults to `--mode benchmark`; full validation requires `--mode full`. The mode hard-gate is intentional: a benchmark cannot be silently misread as a wavelength acceptance.

**Benchmark (2026-05-05, scoping only — superseded by the running full-mode run; benchmark numbers are not a wavelength decision)**:
- Configuration: n=384, domain_size=384, dx=1, dt=0.05, seed=2026050400, noise_scale=1e-4. Steps run: 20. Elapsed: 12.75 s; per-1000-step rate: 637.4 s. Projected ≥4.25 h for the minimum 24 000-step run before saturation criterion extends it. CG iteration ceilings: u-side 4, v-side 51. All solves converged. termination_reason = benchmark_complete. Early FFT wavelength at step 20: 16.198 — NOT a V004-B result; the run had not reached nonlinear saturation; recorded for traceability only.
- Local artifacts: `validation/04_fv_nonlinear_wavelength_benchmark.csv`, `.json`, `.png`, `_report.md`.

**Method (full mode, unchanged)**: with the V004-A-passing solver, run nonlinear pattern formation on a rectangular subdomain to convergence. Measure dominant realized wavelength via 2D FFT.

**Acceptance (unchanged)**: realized wavelength within 5% of ≈19.2 grid units (i.e., 18.24–20.16).

**Severity rule (unchanged)**: if V004-B fails despite V004-A passing, the nonlinear regime of the new solver disagrees with the spectral baseline; this is a solver-level discrepancy that must be resolved before any geometry claim. Do not advance.

### V004-C — One-seed masked-digit boundary diagnostic — *DIAGNOSTIC ONLY*

**Status**: pending. Blocked behind V004-B pass.

**Method**: with the V004-A and V004-B-passing solver, run one seed (2026050400) on the masked digit domain (width 96, length 192, cap radius 48). Measure median angle between activator wavevector and local boundary tangent in three annuli inside the cap: 0–0.5λ, 0.5–1λ, 1–2λ.

**Purpose**: characterize how the boundary regime transitions between near-boundary and far-boundary behavior under the proper geometric solver. Provides information for understanding V004-D outcome; does *not* set or move the acceptance bar.

**Severity rule**: V004-C is informational. It does not gate V004-D. The V004-D acceptance bar is fixed at the same value as the rejected prototype's predeclared rule. **V004-C results are not grounds for adjusting V004-D.**

### V004-D — Rerun original Gate 004 with unchanged criterion

**Status**: pending. Blocked behind V004-A and V004-B pass.

**Method**: with the V004-A and V004-B-passing solver, rerun the original Gate 004 protocol. Geometry, seeds, and acceptance rule are unchanged from the rejected prototype:
- Geometry: width 96, total length 192, half-disk cap radius 48.
- Seeds: 2026050400, 2026050401, 2026050402, 2026050403, 2026050404. Identical, unchanged.
- Acceptance rule: median angle between activator wavevector and local boundary tangent in [70°, 110°] in the 1–2λ annulus inside the cap, for ≥4/5 seeds. Identical, unchanged.
- `dt` revised to V004-A-validated value (0.05) or smaller; revision logged. step count and `noise_scale` matched to prototype unless V004-B requires revision.

**Wallclock note (provisional, from V004-B benchmark)**: V004-D operates on the masked digit domain (~14 000 active cells) which is roughly an order of magnitude smaller than V004-B's L=384, n=384 substrate (147 456 cells). At V004-B's per-cell rate, V004-D's 5-seed ensemble should be substantially cheaper than V004-B itself. V004-D is not the wallclock long-pole.

**Outcome**: V004-D pass closes B2 and authorizes B3. V004-D fail with V004-A and V004-B both passing means the geometric coupling needed to produce fingerprint-like reorientation is not present at these published parameters on this geometry — a substantive finding, **not** a methods failure, and grounds for genuine biological reinterpretation. **In neither case is the V004-D bar moved.**

## Five-stage program

### B1 — Validation provenance and canonical kinetics

**Status**: closed.

### B2 — Masked digit geometry Gate 004

**Status**: open. Lightweight nearest-active-cell prototype rejected 2026-05-05. Decomposed into V004 ladder. **V004-A passed; V004-B running in full mode (in-progress, not accepted, not rejected).** B2 closes only when V004-D passes its unchanged acceptance rule.

### B3 — Digit-size scaling ensemble

**Status**: blocked behind V004-D pass.

### B4 — Empirical dermatoglyphic data anchor

**Status**: blocked behind B3.

### B5 — Manuscript evidence map

**Status**: blocked behind B3 + B4.

## Falsification gates (unchanged)

Any of the following stops the program:

1. Reproduction of Glover 2023 Fig 5 patterns from published parameters fails after ~2 weeks of implementation effort. *(Not yet triggered.)*
2. Forensic ridge-count data is too inconsistent across cohorts to support quantitative comparison. *(Not yet checked.)*
3. Turing wavelength on small-digit domain ≥ digit width. *(Not yet checked.)*
4. A 2024–2026 paper has already done fixed-parameter digit-scaling of the Glover model. *(Targeted scan to date: no obvious hit; final scan before B3.)*

Gate 004 prototype rejection is **not** a falsification gate — it is a methods gate. V004-D fail with V004-A/B pass *would* be a substantive finding (not a falsification of the program, but a constraint on the published parameters' geometric portability). Distinction preserved.

## Platform-side dependencies

- SOP-RXD-001 clearance for the execution surface.
- [[PR-011]] — goals retract/tag-clear.
- [[PR-012]] — file_bug dry_run contract.
- [[PR-017]] — external-run attestation primitive (covers *completed* external runs; append-once postcondition fields).
- [[PR-030]] — in-progress external long-run heartbeat primitive (covers *running* external runs; updatable liveness fields). Sibling to PR-017, not duplicate.
- [[PR-018]] — Goal hierarchy / milestone primitive.
- BUG-063 — wiki promote sources lint (no longer triggers since the page is updated in-place after first promotion).

## Cross-references

- [[PR-011]] — Goals retract/tag-clear
- [[PR-012]] — wiki file_bug dry_run contract
- [[PR-017]] — external-run attestation primitive (completed-run scope)
- [[PR-030]] — external long-run heartbeat primitive (in-progress scope)
- [[PR-018]] — Goal hierarchy/milestone primitive
- Goal `cbc96a78d7ff` — this program's Goal anchor
- SOP-RXD-001 — re-evaluation protocol for connector trust
