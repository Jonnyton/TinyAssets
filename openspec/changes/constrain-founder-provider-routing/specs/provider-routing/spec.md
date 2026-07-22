## ADDED Requirements

### Requirement: Engine assignment establishes a fail-closed provider eligibility ceiling
A founder-authorized `set_engine` assignment SHALL replace the universe's `allowed_providers` with the exact persistent provider-destination set selected by that assignment. `allowed_providers` is an eligibility ceiling, not preference, credential ownership, request execution authority, auth health, or proof that execution can succeed. `preferred_writer` SHALL only order providers already inside the ceiling and SHALL NOT add a provider, rescue an empty ceiling, or authorize fallback. `allowed_providers=None` remains the legacy/unassigned state; an empty list records an engine choice whose executable destination is not yet complete or whose assignment is quarantined. Before each normal, policy, or judge provider attempt for an explicit universe, routing SHALL acquire the universe's assignment lock and re-read the non-secret on-disk assignment state. Missing/invalid/`pending` state, a non-`list[str]` ceiling, or a candidate outside the fresh ceiling SHALL fail or hold before provider/quota/auth-health access. Only `engine_assignment_state="ready"` with an explicit valid ceiling may pass this boundary. This persistent boundary is necessary but not sufficient request execution authority.

#### Scenario: BYO assignment persists a singleton eligible provider
- **WHEN** a founder successfully assigns an Anthropic key with no explicit preferred writer
- **THEN** the universe config stores `preferred_writer="claude-code"` and `allowed_providers=["claude-code"]`
- **AND** an OpenAI key analogously stores `codex` as both values

#### Scenario: Incomplete engine sources establish an empty ceiling
- **WHEN** a founder records `self_hosted_endpoint`, `market_rented`, or `host_daemon` before its source-specific authority is executable and bound
- **THEN** `set_engine` stores `allowed_providers=[]`
- **AND** provider-backed work fails or holds without invoking the ordinary fallback chain

#### Scenario: Reassignment replaces rather than unions the ceiling
- **WHEN** a founder reassigns an Anthropic BYO engine to an OpenAI BYO engine
- **THEN** `allowed_providers` changes from `["claude-code"]` to `["codex"]`
- **AND** `claude-code` is no longer eligible

#### Scenario: Preference outside the derived ceiling is rejected before mutation
- **WHEN** an Anthropic key is submitted with `preferred_writer="codex"`
- **THEN** the assignment returns an error naming `claude-code` as the matching provider
- **AND** the prior vault, engine fields, preference, and allowlist remain unchanged

#### Scenario: Assigned BYO provider failure never falls through
- **WHEN** the provider selected by a BYO assignment fails while other providers are registered and healthy
- **THEN** routing raises `AllProvidersExhaustedError`
- **AND** every provider outside the assignment's singleton allowlist remains uncalled

#### Scenario: Historical assignments are migrated before rollout
- **WHEN** inventory finds a historical `set_engine` assignment without an explicit ceiling
- **THEN** a reviewed confirmed BYO mapping is explicitly migrated to its singleton ceiling
- **AND** an ambiguous or incomplete assignment is migrated to `allowed_providers=[]`
- **AND** rollout remains blocked while any historical assignment is unclassified or unmigrated

#### Scenario: Stale context cannot bypass an assignment in progress
- **WHEN** a request captured a prior ready context and reassignment has since stored `engine_assignment_state="pending"` with `allowed_providers=[]`
- **THEN** normal, policy, and judge routing re-read the fresh state under the assignment lock and invoke zero providers
- **AND** after commit or rollback, a stale context still cannot invoke a provider outside the fresh on-disk ceiling

#### Scenario: Malformed or legacy non-secret assignment state fails closed
- **WHEN** an explicit universe has missing/invalid assignment state or an allowlist that is `None`, scalar, or contains non-string entries
- **THEN** normal, policy, and judge routing invokes zero providers and reports setup or repair required
- **AND** no vault inspection, ambient auth, preference, health, or local reachability widens eligibility
