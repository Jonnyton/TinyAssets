## ADDED Requirements

### Requirement: First-contact execution uses only a complete requester-authorized resource bundle
Before the universe intelligence generates a provider-backed reply, the server SHALL resolve a complete request-scoped authority bundle containing requester-owned compute or requester-accepted market compute and, when the workload requires model access separately, requester-owned model access or a requester-accepted market model grant. A provider credential MAY satisfy both elements only when it is owned by the requester or conveyed by the requester's accepted market grant. Project-maintainer, project-founder, and platform-operator credentials, quota, auth homes, hardware, and accounts SHALL never be eligible for another user's workload.

#### Scenario: requester-owned bundle permits a reply
- **WHEN** first contact has requester-owned compute and all separately required requester-owned model access
- **THEN** the universe intelligence may generate its first-person reply using that bundle
- **AND** the chatbot relays and renders the universe intelligence's reply without authoring it

#### Scenario: accepted-market bundle permits a reply
- **WHEN** the requester has accepted market grants that provide compute and all separately required model access
- **THEN** the universe intelligence may generate its reply using only resources conveyed by those accepted grants

#### Scenario: maintainer resources are never a fallback
- **WHEN** a complete requester-owned or accepted-market bundle is unavailable but project-maintainer, project-founder, or platform-operator credentials, quota, auth homes, hardware, or accounts are reachable by the host process
- **THEN** none of those resources is eligible and no provider is invoked with them

### Requirement: Provider routing and fallback remain inside the authorized bundle
Provider selection, retry, and fallback SHALL use only providers admitted by the immutable request authority bundle. Routing SHALL NOT rediscover ambient credentials, cloud chains, local subscription auth, host accounts, or hardware after the authority decision, and SHALL hold execution when the admitted provider set is empty.

#### Scenario: fallback stays within the bundle
- **WHEN** the selected authorized provider fails and another provider admitted by the same bundle is available
- **THEN** fallback may try only that admitted provider

#### Scenario: fallback cannot escape the bundle
- **WHEN** every provider admitted by the authority bundle is unavailable and an ambient host provider is reachable
- **THEN** the request is held without invoking the ambient host provider

### Requirement: Missing or partial authority holds execution after birth
Universe birth and founder-home binding SHALL be allowed to complete without compute, but provider-backed execution SHALL NOT begin unless the authority bundle is complete. A missing or partial bundle SHALL return a structured result with `status: held`, `reason: setup_required`, the materialized `universe_id` when birth completed, the missing `compute` and/or `model_access` elements, and requester-facing BYOC and accepted-market setup paths; it SHALL NOT return generic `provider_exhausted` or fabricate a universe reply.

#### Scenario: missing authority births without execution
- **WHEN** an authenticated founder's opening `converse` births and binds a home but no eligible compute or model authority exists
- **THEN** birth remains complete, no provider is invoked, and the structured setup-required hold identifies both missing elements and the new `universe_id`

#### Scenario: partial authority does not invoke a provider
- **WHEN** requester-owned or accepted-market compute exists but separately required model access does not
- **THEN** no provider is invoked and the structured hold identifies `model_access` as missing

### Requirement: Reply generation and learning extraction share the same authority boundary
The server SHALL authorize both the universe intelligence's reply generation and any model-backed learning extraction against the same immutable request authority bundle. The phases MAY select different providers admitted by that bundle for their respective work, but neither phase SHALL use a provider or resource outside the bundle. Each invocation SHALL record a redacted receipt containing its phase, provider identity, and authority class of `requester_owned` or `accepted_market` without recording a secret.

#### Scenario: both phases use the same bundle
- **WHEN** reply generation and learning extraction both run for one first-contact turn
- **THEN** both invocations use providers admitted by the same authority bundle, whether or not they select the same provider
- **AND** separate linked receipts identify each phase, provider, and authority class

#### Scenario: uncovered extraction is held
- **WHEN** the authority bundle covers reply generation but does not cover a separately gated learning-extraction invocation
- **THEN** the reply may be relayed but extraction is held without using ambient maintainer resources
