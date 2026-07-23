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

### Requirement: The fantasy domain declares its exact episodic coordinates
Loading the fantasy memory-schema module SHALL register domain `fantasy_author` with ordered episodic coordinate fields `book_number`, `chapter_number`, and `scene_number`, and SHALL identify `chapter_number` as its sequence field. The definition SHALL live in the domain module and use the engine registry rather than embedding fantasy coordinate names in shared memory storage.

#### Scenario: Fantasy coordinate registration is discoverable
- **WHEN** the fantasy memory-schema module is loaded
- **THEN** resolving `fantasy_author` returns the three ordered coordinate fields and `sequence_field=chapter_number`

### Requirement: Accepted fantasy commits emit a typed ScenePacket companion
The fantasy commit path SHALL serialize a `ScenePacket` JSON companion next to scene prose at `output/book-<book>/chapter-<chapter:02d>/scene-<scene:02d>.packet.json` when `_universe_path` is present. The packet schema SHALL include scene/universe identity; book, chapter, and scene position; optional POV, location, and time; string participants; introduced/changed facts; opened/advanced/resolved promises; relationship and world-state deltas; optional editorial verdict; word-count/revision metrics; provider provenance; and enrichment signals with the current `worldbuild_signals` same-arc alias. The current emitter SHALL populate available orient/fact/promise/editorial/metric/signal fields and leave unavailable schema fields at their typed defaults.

#### Scenario: Commit writes the packet beside prose
- **WHEN** commit emission receives a universe path and scene coordinates
- **THEN** it writes the JSON packet at the matching book/chapter/scene companion path with the supplied identity, coordinates, word count, and revision flag

#### Scenario: Participants are normalized to strings
- **WHEN** orient characters are dictionaries or non-empty strings
- **THEN** the packet's participant list contains only the resolved name, character id, id, or original string for each participant

#### Scenario: Facts and promises retain typed evidence
- **WHEN** commit receives extracted fact objects or dictionaries and promise dictionaries
- **THEN** the packet serializes typed fact references and opened promise references with current default confidence/importance behavior

#### Scenario: Signal alias remains mirrored
- **WHEN** a packet is constructed with only `enrichment_signals` or only `worldbuild_signals`
- **THEN** its post-initialization mirrors that list into the other same-arc alias field

#### Scenario: Missing universe path skips emission
- **WHEN** commit state has no `_universe_path`
- **THEN** ScenePacket emission returns without writing and without raising
