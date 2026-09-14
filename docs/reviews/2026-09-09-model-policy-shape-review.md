# Model-policy kernel: independent shape review

September 9, 2026. Claude read-only review, exit 0 after 216 seconds, verdict
ADAPT. The earlier broad authority/tool-loop review timed out at 480 seconds
without a verdict and is not approval. This receipt covers only an internal pure
ordering module, not storage, public API, execution admission or deployment.

## Lead disposition

Accept privacy filtering, executor-level tool capability, source-wide freshness,
single designated benchmark source, explicit stable preference, trustworthy
account grouping, exact integer prices and no dispatch/authority in the output.

One disagreement with the proposed three-tier fallback sequence: a current
selection overrides the saved default; it does not implicitly consent to falling
back to that default. The primary is current selection if present, otherwise
saved default. Only explicitly accepted fallbacks follow it, including an empty
list. This preserves the owner's independently editable fallback sequence and
the spec's fail-closed empty-sequence scenario. Test this with both a current
selection and a different saved default present.

Stale explicit choices remain visible advisory entries with refresh labels,
never executable authorization. Known incompatible, non-free or excessive-price
choices remain ineligible even when explicitly chosen. Future dispatch must
refresh and enforce authority, privacy, capability and cost independently.

## Independent verdict

Scope held. I read only the design document and the two delta specs. Findings are limited to the pure policy module and its tests.

## Contract points against the cited design and specs

- **AGREE**: explicit selection then accepted fallback order wins, and an empty list is fail-closed. Design decision 4 and the "No accepted fallback" scenario say this directly.
- **DISAGREE_EVIDENCE**: the contract collapses three explicit tiers into two. Design decision 3 orders "explicit current choice then saved default/order", and the selection spec requires switching, saving a default and ordering fallbacks to be independent. The policy input needs current selection, saved default and fallbacks as separate fields, with the explicit sequence being current, then saved default, then fallbacks, deduplicated. The design wording is loose here, so the module must make that ordering explicit and tested rather than collapse it.
- **AGREE**: subscription and local sources first using the advertised default, then aggregator ranking, with unknown scores never invented. Design decision 3 says this and adds that context size and newer names are not quality scores, so the opacity test below must cover those fields too.
- **DISAGREE_EVIDENCE**: the contract omits privacy. Design decision 3 ranks aggregator candidates "within capabilities, privacy and permitted cost", and the source check relies on the owner-filtered catalogue endpoint. The snapshot needs a field stating whether it came from the owner-filtered catalogue. Automatic aggregator candidates from an unfiltered snapshot are ineligible.
- **DISAGREE_EVIDENCE**: model tool support alone is not enough. The design context says the open HTTP executor has no engine-tool loop, and the risk section forbids marking full-agent readiness on text-only success. The snapshot needs a connection-level executor capability declaration. A tool-requiring interaction on an executor without a tool loop is ineligible with its own reason.
- **AGREE**: free-only means confirmed zero for every required charge component. The "Free model withdrawn" scenario and the design risk on withdrawn free tiers support this. The module needs an interaction requirements input listing the charge components. A missing or unconfirmed component is not free.
- **DISAGREE_CONCERN**: "automatic HTTP candidate" keys the staleness rule on transport. The design keys freshness at the connection snapshot boundary, and local daemons are also HTTP. Key the rule on mode plus freshness instead. In automatic mode every candidate needs fresh capability evidence, and metered candidates need fresh confirmed price. Explicit candidates with stale evidence are emitted with a stale label because runtime admission revalidates.
- **DISAGREE_CONCERN**: "comparable" scores as a pairwise test yield a partial order, and a partial comparator fed to a sort is not deterministic. Take a single designated ranking source as input and bucket. Ranked candidates have a fresh agentic score from that source, sorted by agentic, then general, then the stable preference, then input index. Unranked candidates follow in input order. Scores from any other source are treated as absent.
- **DISAGREE_CONCERN**: "current suitable default" must be an explicit input to a pure module, used only as a tie-breaker and never read from the serving binding.
- **AGREE**: model-local exhaustion skips one candidate, account-wide exhaustion excludes the shared capacity key, and unknown identity is not proof of independence. Design decision 5 and the "Account allowance exhausted" scenario support this. The capacity key needs a trust level so unknown identity collapses to the connection and cannot promote a sibling unverified connection to the same provider.
- **AGREE**: dedup bounds attempts. Dedup on capacity key plus model id so the same model through two keys of one authenticated account is one candidate.
- **AGREE**: no dispatch and no workflow mutation. Enforce with no clock, no randomness and an import-boundary test.

## Concrete shape changes

```
Snapshot { connectionId, sourceKind: subscription|local|aggregator,
  freshness: fresh|stale|missing,          // computed upstream; module takes no clock
  ownerFiltered: boolean, executor: { toolLoop: boolean },
  capacityKey: { trust: authenticated, provider, accountId }
             | { trust: unverified, provider, connectionId },
  advertisedDefaultModelId?, models: Model[] }
Model { modelId /* opaque, never parsed */,
  capabilities: { tools: true|false|unknown, modalities, contextTokens? },
  pricing: { kind: unmetered } | { kind: unknown }
         | { kind: metered, components: Record<Component, { amountMicros: int, confirmed: bool }> },
  scores?: { source, agentic?: int, general?: int } }
Policy { generation, mode, currentSelection?, savedDefault?, fallbacks: Ref[] /* required */,
  costPolicy: free_only | { maxComponentMicros } /* absent means free_only */,
  rankingSource?, stablePreference?: Ref, connectionModelOverrides? }
Interaction { needsTools, modalities, minContext?, chargeComponents: Component[] }
Exhaustion[] { scope: model, ref } | { scope: account, capacityKey }
Output { kind: advisory_order, generation,
  candidates: { ref, basis, evidence: { capability, price, scoreSource? }, labels }[],
  ineligible: { ref /* may be a policy ref absent from the snapshot */, reason, detail? }[] }
```

Reason enum: absent_from_catalogue, stale_capability, stale_price, missing_price_component, not_confirmed_free, exceeds_cost_cap, capability_unsupported, capability_unknown, executor_unsupported, privacy_unverified, model_exhausted, account_exhausted, capacity_identity_unverified, duplicate.

Two further rules. Use integers for money and scores so ties and zero checks are exact across platforms. Name the output advisory and give it no field an admission path could read as a grant.

## Tests to add

- **Opacity**: rewrite every model id, context size and release date with random values and assert the decision structure is unchanged.
- **Free suffix**: an id ending in ":free" with one unconfirmed, nonzero or missing required component is ineligible with the component named.
- **Explicit fail-closed**: selection exhausted with empty fallbacks returns no candidates and one ineligible entry, never an automatic substitute. A selection absent from the snapshot returns an ineligible entry referencing the policy ref.
- **Explicit tiers**: three-tier order and dedup with repeated refs across current, saved default and fallbacks.
- **Stale**: an automatic candidate with stale capability or price is ineligible. The same candidate under explicit mode is emitted with a stale label.
- **Ordering**: equal scores keep input order. The stable preference wins only exact ties. Scores from a non-designated source land in the unranked bucket in input order, and reordering unranked inputs reorders output identically.
- **Capacity**: authenticated account exhaustion excludes the same key across two connections. Unverified identity exhaustion excludes that connection and does not promote another unverified connection to the same provider.
- **Executor**: a tools-capable model on a connection without a tool loop is ineligible for a tool-requiring interaction.
- **Purity**: the same input twice deep-equals, plus a static check that the module imports no clock, random, storage or network module.

VERDICT: ADAPT
