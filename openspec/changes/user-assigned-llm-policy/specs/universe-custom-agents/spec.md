## ADDED Requirements

### Requirement: Bindings carry a private provider policy that stays out of the public definition

A universe binding SHALL be able to carry a provider policy consisting of a
preferred provider and an ordered list of accepted fallbacks. That policy is
private operational configuration: it SHALL NOT appear in the public agent
definition, its portable export, or its remix lineage, and it SHALL carry only
nominal provider identifiers, never a credential or credential reference.

#### Scenario: policy stays private on publish
- **WHEN** an agent whose binding declares a provider policy is published or exported
- **THEN** the public definition and the portable export contain no provider policy and no provider identifier from that binding

#### Scenario: policy does not transfer on remix
- **WHEN** a second account remixes the public definition
- **THEN** the remix carries no provider policy from the first owner's binding

#### Scenario: credential-shaped policy value is refused
- **WHEN** a binding provider policy carries a credential- or bearer-shaped value
- **THEN** the binding write is rejected and nothing is persisted

### Requirement: Workflow provider policy resolves fail-closed within the universe selection

A binding's provider policy SHALL resolve as the intersection of that policy, the
universe's provider selection, and the enrolled requester-owned provider set. The
policy SHALL NOT reach a provider the universe selection excludes. An empty
accepted-fallbacks list SHALL mean only the preferred provider may serve the
work. An empty intersection SHALL fail closed with an error naming which input
produced it.

#### Scenario: binding cannot escape the universe selection
- **WHEN** a binding declares a preferred provider that the universe selection excludes
- **THEN** resolution fails closed and the excluded provider is not invoked

#### Scenario: no accepted fallback means no substitution
- **WHEN** a binding declares a preferred provider with no accepted fallbacks and that provider is unavailable
- **THEN** the work fails closed and no other provider is invoked

#### Scenario: empty intersection names its cause
- **WHEN** the effective provider set for a binding resolves empty
- **THEN** the error names whether the binding policy, the universe selection, or the enrolled set produced the empty result
