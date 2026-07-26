## ADDED Requirements

### Requirement: Task Automation Is User-Authored Primitive Composition

TinyAssets SHALL expose domain-agnostic composition and execution primitives
without shipping a privileged bug-investigation, patch-shipping, or recurring
task loop. Investigation, patch generation, scheduling, shipping, and other
automation SHALL run only as user-authored workflows under the same identity,
authority, execution, and effect rules as other graph designs. Authors MAY
publish those designs to the commons for copying, remixing, or combination.

#### Scenario: Filing does not select a platform-owned workflow

- **WHEN** a user files a bug, feature, design, or patch-request page
- **THEN** TinyAssets does not select, enqueue, or execute a platform-owned
  investigation or shipping workflow
- **AND** any later automation requires an explicit user-authored composition

#### Scenario: A user composes automation from generic primitives

- **WHEN** an authorized user wants to connect intake, graph execution,
  evaluation, and an external or wiki effect
- **THEN** the user can design or install a workflow composed from the ordinary
  primitives that are available to other graph designs
- **AND** the workflow receives no hidden product-specific action, request type,
  credential, or effect authority

#### Scenario: Generic completed-run reuse has no packet writeback

- **WHEN** a generic branch task reuses a matching completed durable run
- **THEN** the executor may return its ordinary reused-run evidence without
  executing again
- **AND** it does not interpret output field names as authority to mutate a wiki
  page or repository
