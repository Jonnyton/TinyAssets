## ADDED Requirements

### Requirement: The public advertised descriptions are independent of the engine surface

The public connector handles and the served engine handles SHALL carry
independent descriptions. Relocating guidance on the engine surface SHALL NOT
change what the public endpoint advertises, because chatbot clients read the
public surface and the canonical handle set is the thing the canary guards.
Measured 2026-09-25: the public `write_graph` description is 16,623 chars and the
engine's is 38,513 — two docstrings on two functions, and they SHALL stay
uncoupled.

#### Scenario: an engine-side relocation leaves the public description alone
- **WHEN** long-form guidance moves out of an engine handle's advertised description
- **THEN** the public connector's description for the same handle name is unchanged
- **AND** the canonical advertised handle set is unchanged

#### Scenario: the two surfaces are not silently coupled
- **WHEN** the public and engine descriptions for a shared handle name are compared
- **THEN** neither is derived from the other, so editing one cannot alter the other
