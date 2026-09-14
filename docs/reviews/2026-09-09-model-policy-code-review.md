# Advisory kernel code review and adaptation

Independent Claude review, September9, 2026, exit0 after281s. Exact reviewed
commit434285214bd466f5225a316a5aaa3e84b0cf8f35. This is not rollout approval.

## Adaptation

Added six regression cases that fail against the reviewed implementation, then
fixed the evidence defaults, eager contradictory-price validation, mode/primary
validation, missing native-default reporting and unverified sibling-key retries.
Confirmed prices and caps now require explicit True. All40 policy tests pass.
The input-immutability assertion now compares a deep copy, and ranked opacity is
tested as well as unranked opacity. No live integration or authority change.

Future integration must treat stale labels as refresh-required, re-evaluate
accumulated exhaustion after each failed attempt, validate policy/catalogue/
exhaustion scope and live generation, and never treat advisory output as a grant.
Errors must surface as held/error state, not a silent fallback path. Existing
live custody, permissions, price and tool capability checks remain mandatory.

## Independent result

Commit resolved from the checkout: full SHA `434285214bd466f5225a316a5aaa3e84b0cf8f35` (short `43428521`, "Build advisory agent model selection policy"). The three files are clean at HEAD. I read only those files and did not execute anything. The 33-test count matches the parametrization arithmetic in the test file. The 15 mirror tests, the Ubuntu run, and the ruff/build claims are outside the three files and are unverified here.

**AGREE**

- **Deterministic ordering.** Automatic refs come from an insertion-ordered dict built in catalogue order, and the final sort is Python's stable sort with a total key at `tinyassets/providers/model_policy.py:310`. Sets are used for membership only, and the first failing charge component is chosen via a sorted iteration at line 189. The trace of the ranking test at `tests/test_model_policy.py:205` matches the expected sequence exactly, including the stable-preference behaviour for exact ties and for unranked models.
- **Explicit choice.** Current overrides saved primary at line 243, fallbacks follow only when listed, and an empty accepted sequence stays empty. Explicit choice bypasses only freshness, never privacy, executor, capability, or price. Absent or exhausted explicit refs land in `ineligible` with no automatic substitute. Tests at lines 77, 92, 101, 109 and 176 cover each of these.
- **Privacy and tool capability.** Owner filtering is the first gate at line 165, executor tool loop is checked before model tool flag, and unknown tool support is its own reason. Both modes are tested at line 137.
- **Free-only and caps.** Free-only requires every required component present, confirmed and exactly zero. Caps require a confirmed cap for every required component. Empty required components fail closed with a named detail. Unmetered bypasses component checks but not freshness in automatic mode.
- **Exhaustion and dedup.** Capacity identity collapses to the connection when unauthenticated, account exhaustion refuses to promote an unverified sibling on the same provider, dedup keys on identity plus model id and is only recorded for eligible entries. Output size is bounded by the ref list. Tests at lines 255 through 289 trace correctly.

**DISAGREE_CONCERN**

- **Fail-open default.** `Charge.confirmed` defaults to `True` at `tinyassets/providers/model_policy.py:28`. Every other evidence field is required or defaults closed. An adapter that maps prices without thinking about confirmation gets confirmed prices for free. Remove the default or default it to `False`. The fixtures at test lines 25 and 181 rely on the default and would need explicit values.
- **Mode precedence is implicit.** At line 244 any primary forces explicit regardless of `mode`, and `mode="automatic"` with fallbacks but no primary silently drops the fallbacks. Document `mode` as "behaviour when no primary is present" on the dataclass, or reject the contradictory combination in `__post_init__`.
- **Asymmetric unverified rule.** Model-scope exhaustion on an unauthenticated connection does not exclude an unauthenticated sibling with the same model id, while account scope does. Finite, but it permits one extra attempt per sibling. State this as intended in the doc or apply the same rule.
- **Lazy validation.** Duplicate `cost_caps` components raise only when some candidate reaches line 188, and `Pricing(unmetered=True, charges=nonzero)` is never rejected. Move both checks into `__post_init__`.
- **Silent omission.** A subscription or local connection whose advertised default is missing or absent from its model list produces no candidate and no `ineligible` entry in automatic mode.

**Test claim mistakes**

- The test at line 318 is named "does_not_modify_inputs" but asserts nothing about the inputs. Immutability is guaranteed by frozen dataclasses, not by this test.
- The opacity test at line 234 only exercises the unranked bucket. It does not show that ranked ordering is invariant under id or context rewrites.

**MUST be enforced before a dispatcher consumes the output**

- Treat `refresh_capabilities` and `refresh_price` labels as blocking. Explicit stale candidates are emitted as candidates, not ineligible, and the kernel does not re-verify them.
- Re-run the kernel with accumulated `Exhaustion` evidence after every failure. Walking the original candidate list past a failure bypasses the unverified-identity protection, which lives only in re-evaluation.
- Compare `AdvisoryOrder.generation` to the live policy generation and discard on mismatch. The output carries no owner, universe or catalogue binding.
- Treat any `ValueError` from the kernel as zero candidates. Never fall through to another selection path.
- Guarantee the policy and exhaustion evidence were loaded for the same owner and universe as the catalogue. `ModelPolicy` carries no scope, so the kernel cannot check this.
- Dispatch only from `candidates`. `ineligible` is display data. Refresh authority, privacy, capability and price at admission as the module docstring requires.

VERDICT: ADAPT
