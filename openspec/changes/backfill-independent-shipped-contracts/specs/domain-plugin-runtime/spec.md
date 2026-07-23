## ADDED Requirements

### Requirement: Domains register their own discoverable Branch slugs
The engine-side domain registry SHALL accept trimmed non-empty `(domain_id, branch_slug)` registrations, deduplicate them per domain, and return sorted slugs either for one domain or as the union across all domains. The Goal-pool producer SHALL combine registered domain slugs with catalog-visible slugs without naming a built-in domain; when the combined accessible set is non-empty it SHALL skip tasks for absent slugs, and when the set is empty it SHALL preserve the current fail-open behavior.

#### Scenario: Registered slug makes a domain seed accessible
- **WHEN** a domain registers its wrapper Branch slug and a subscribed Goal-pool row targets that slug
- **THEN** the producer accepts the row without core producer code hard-coding the domain name

#### Scenario: Unregistered slug is filtered when accessibility is known
- **WHEN** at least one accessible Branch is known but a Goal-pool row targets an unregistered and uncatalogued slug
- **THEN** the producer skips that row

#### Scenario: Empty accessibility discovery fails open
- **WHEN** no catalog or registered domain slugs can be discovered
- **THEN** the producer does not treat the empty set as proof that a target slug is inaccessible

### Requirement: Domains register episodic coordinate shapes without changing shared storage
The domain registry SHALL store one `EpisodicCoordinateShape` per `domain_id`, preserving the registered coordinate fields as an ordered tuple and an optional sequence field. Resolving an unknown domain SHALL return no shape, and registering the same domain again SHALL replace its prior shape. Clearing the test registry SHALL clear callable, Branch-slug, and episodic-shape state.

#### Scenario: Coordinate shape round-trips
- **WHEN** a domain registers coordinate fields and a sequence field
- **THEN** resolution returns the same domain id, ordered tuple of coordinate fields, and sequence field

#### Scenario: Re-registration replaces a shape
- **WHEN** the same domain registers a second coordinate shape
- **THEN** subsequent resolution returns only the second shape

#### Scenario: Unknown domain has no engine-imposed coordinates
- **WHEN** no episodic coordinate shape is registered for a domain
- **THEN** resolution returns `None` and shared episodic storage does not invent domain-specific fields
