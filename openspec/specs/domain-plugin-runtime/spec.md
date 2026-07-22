# domain-plugin-runtime Specification

## Purpose
Define discovery, registration, protocol guidance, and opaque-callable resolution for installed and editable domain plugins.
## Requirements
### Requirement: Domain discovery combines installed and editable sources
The domain runtime SHALL discover installed domains from the `tinyassets.domains` entry-point group and editable-checkout domains from `domains/<name>/skill.py` beside the `tinyassets` package. It SHALL return a sorted, de-duplicated list of names, with an entry-point target taking precedence when both sources report the same name.

#### Scenario: A domain is visible through either supported discovery source
- **WHEN** a package declares a non-empty `tinyassets.domains` entry point or an editable checkout contains `domains/<name>/skill.py`
- **THEN** `discover_domains()` includes the corresponding domain name exactly once
- **AND** the returned names are sorted

#### Scenario: Installed metadata cannot be read
- **WHEN** the entry-point metadata lookup raises an exception
- **THEN** discovery treats the entry-point source as empty
- **AND** filesystem discovery remains available without propagating that metadata exception

### Requirement: Auto-registration resolves domains without collapsing the registry
The domain runtime SHALL instantiate an entry-point target expressed as `module:attribute` when one is available, otherwise it SHALL use the editable `domains.<name>.skill` fallback heuristic. It MUST isolate a malformed target, import failure, missing class, or registration exception to that domain and continue attempting other discovered domains.

#### Scenario: A valid installed entry point is registered
- **WHEN** discovery finds `probe = "pkg.probe.skill:ProbeDomain"`
- **THEN** `auto_register()` imports `pkg.probe.skill`, instantiates `ProbeDomain`, and passes the instance to the supplied registry

#### Scenario: One discovered domain is invalid
- **WHEN** one entry-point target is malformed or its import or registration fails
- **THEN** that domain is skipped with a warning
- **AND** a later valid discovered domain can still be registered

### Requirement: Registry identity derives from domain configuration
The concrete domain registry SHALL store a registered domain by `domain.config["name"]`, list stored names in sorted order, and return `None` for an absent name. It MUST reject an object with no usable dictionary `config` containing `name`; registering another object with the same configured name replaces the prior object.

#### Scenario: Reference domains are auto-registered under their configured identities
- **WHEN** the reference domains are discovered and registered
- **THEN** the registry can retrieve `fantasy_author` and `research_probe`
- **AND** `list_domains()` returns their configured names in sorted order

#### Scenario: A domain does not provide valid registration metadata
- **WHEN** `register()` receives an object with no `config`, or whose resolved config is not a dictionary containing `name`
- **THEN** registration raises `ValueError`
- **AND** no registry entry is created from that object

### Requirement: Domain-owned opaque callables use an engine-side registry
The runtime SHALL resolve a domain-owned opaque callable by the exact `(domain_id, node_id)` pair. It MUST allow re-registering that pair by replacing the previous callable, and branch compilation MUST reject a body-less node for which no matching callable is registered rather than defer the failure to execution.

#### Scenario: A registered opaque node compiles and invokes its domain callable
- **WHEN** a domain registers a callable for a body-less node's exact domain and node identifiers
- **THEN** compilation resolves that callable
- **AND** invoking the compiled node returns the callable's state updates

#### Scenario: A body-less node has no registered callable
- **WHEN** compilation receives a body-less node without a matching `(domain_id, node_id)` registration
- **THEN** compilation raises `CompilerError`
- **AND** it does not produce a silent pass-through node

### Requirement: The published protocol is the current domain integration shape
The domain integration contract SHALL expose protocol shapes for domain configuration, graph construction, state extensions, tools, evaluation criteria, memory schemas, optional API routes, and registry operations. It MUST treat those protocols as typing/interface guidance rather than a runtime conformance validator; the concrete registry currently enforces only the `config`-dictionary-and-name registration boundary.

#### Scenario: A reference domain supplies the current contract shape
- **WHEN** a caller constructs `FantasyAuthorDomain` or `ResearchProbeDomain`
- **THEN** it exposes configuration with a non-empty name, description, and version
- **AND** its domain implementation can provide graph, state-extension, tool, evaluation, and memory integration methods defined by the protocol surface

#### Scenario: An object bypasses unvalidated protocol members
- **WHEN** an object provides a dictionary config with `name` but omits other protocol methods
- **THEN** the concrete registry can accept it
- **AND** registration alone does not prove full `Domain` protocol conformance

### Requirement: Current discovery and naming limitations remain explicit
The as-built domain runtime MUST NOT claim transactional registration, thread-safe registration writes, third-party filesystem scanning outside the editable checkout, or a single canonical identifier shared by discovery and registry. In particular, it SHALL preserve the current reference mapping from entry-point name `fantasy_daemon` to registry configuration name `fantasy_author` until a separate compatibility change alters it.

#### Scenario: Discovery and registry expose the legacy reference-name mapping
- **WHEN** the built-in entry-point table is inspected or `discover_domains()` is called
- **THEN** it includes `fantasy_daemon`
- **AND** after registration the same implementation is retrieved as `fantasy_author`
- **AND** callers do not infer those two names are currently interchangeable registry keys
