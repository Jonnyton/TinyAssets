## ADDED Requirements

### Requirement: Domains register discoverable Branch slugs without core domain knowledge

The engine-side domain registry SHALL accept Branch slugs under a non-empty stripped domain identifier, ignore registrations with an empty stripped domain or slug, and de-duplicate repeated slugs within each domain. It SHALL return sorted immutable tuples either for one stripped domain identifier or for the de-duplicated union of every registered domain. The registry MUST remain process-local and MUST NOT imply that an unloaded domain's branches are registered or accessible.

#### Scenario: One domain registers repeated Branch slugs

- **WHEN** a domain registers non-empty slugs, including the same slug more than once
- **THEN** querying that domain returns each registered slug once in sorted order
- **AND** blank identifiers or slugs contribute no entry

#### Scenario: All domain Branch slugs are requested

- **WHEN** multiple domains have registered Branch slugs and the caller omits a domain filter
- **THEN** the registry returns the sorted de-duplicated union
- **AND** it does not invent slugs for domains that have not loaded their registrations in this process

### Requirement: Domains declare optional episodic coordinate shapes

The engine-side domain registry SHALL allow a domain to register an `EpisodicCoordinateShape` containing its domain identifier, an ordered tuple of optional coordinate-field names, and an optional sequence-field name. Registration SHALL normalize a supplied list or tuple of coordinate fields into a tuple and SHALL replace the prior in-process shape for the same domain identifier. Resolution SHALL return that frozen shape or `None` when the domain has no registration. The shared episodic storage schema MUST remain domain-neutral; registering a shape MUST NOT add columns, persist metadata, or validate row payloads by itself.

#### Scenario: A domain registers its episodic coordinates

- **WHEN** a domain registers coordinate fields and an optional sequence field
- **THEN** resolution returns a frozen shape with the fields in supplied order as a tuple
- **AND** a later registration for that domain replaces the in-process shape

#### Scenario: No episodic shape is registered

- **WHEN** a caller resolves an unregistered domain identifier
- **THEN** the registry returns `None`
- **AND** shared episodic storage remains usable without domain-specific coordinates
