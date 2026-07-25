## ADDED Requirements

### Requirement: Custody mode is recorded per item and no surface assumes the platform holds the data

Every item a principal owns SHALL carry a recorded custody mode identifying where its content actually lives, drawn from the modes the platform supports and extensible as new modes are researched. Portability and deletion surfaces SHALL read that recorded mode and SHALL NOT assume any default, and in particular SHALL NOT assume the platform holds the content. A surface SHALL NOT be implemented in a way that only functions when custody is platform-held, and SHALL NOT be implemented in a way that presumes the platform never holds private content. An item whose custody mode is unknown SHALL be reported as unknown and handled as not-platform-held, never silently treated as absent or as platform-held.

#### Scenario: Non-platform custody is handled, not ignored

- **WHEN** a principal owns items under a custody mode where the platform does not hold the bytes
- **THEN** those items appear in portability and deletion operations with their custody mode recorded
- **AND** they are neither omitted nor reported as platform-held

#### Scenario: Unknown custody fails safe

- **WHEN** an item's custody mode cannot be determined
- **THEN** it is reported as unknown custody
- **AND** it is treated as not-platform-held for both retrieval and erasure claims

#### Scenario: Neither custody position is hardcoded

- **WHEN** the supported custody modes change as the custody question is researched
- **THEN** portability and deletion continue to function without a change to their contract
- **AND** no requirement depends on the platform either always or never holding private content

### Requirement: The custody manifest is itself custody-mode-scoped and the platform is not assumed to own the inventory

The item-and-holder manifest that export and deletion depend on SHALL NOT be assumed to be a platform-owned global inventory of a principal's items. The platform's own records SHALL be limited to what it can legitimately know: the items it holds itself, and a **holder registration** for each non-platform holder recording the holder's identity, its custody mode, its reachability, and the time it last answered an enumeration. A holder registration SHALL NOT be presented as an inventory of that holder's contents.

A manifest SHALL be assembled at request time as the union of the platform's own records and each reachable holder's own enumeration of what it holds for the requesting principal, and every entry SHALL name the holder that asserted it. Manifest coverage SHALL be stated per custody mode — which holders answered, which deferred, and which cannot enumerate — and a manifest SHALL NOT claim to be a complete inventory of a mode whose holder did not answer. Every "every owned item" guarantee in this capability SHALL be read as scoped to this assembled union together with its coverage statement.

Resolution SHALL be defined per supported mode:

- **Platform-held** — the platform's own records are authoritative and enumerate directly.
- **Private universe brain** — the brain enumerates on request under the owner's authenticated authority; the platform holds the registration, not the contents.
- **Vault** — the vault enumerates under the owner's key authority; the platform holds a reference and SHALL NOT be able to enumerate contents without that authority.
- **Host machine** — the host enumerates when online; when offline the mode's entries are reported deferred under the unavailable-holder contract rather than as absent or complete.

Adding a custody mode SHALL require defining its enumeration resolution the same way, and a mode with no defined resolution SHALL NOT be offered.

#### Scenario: A holder registration is not an inventory

- **WHEN** a principal has items under a non-platform custody mode
- **THEN** the platform's record for that mode names the holder, its mode, and its reachability
- **AND** it does not assert what that holder's contents are

#### Scenario: Coverage is stated per mode, not implied

- **WHEN** one holder answers the enumeration and another is unreachable
- **THEN** the manifest states the answering holder's coverage and marks the unreachable holder's coverage as deferred
- **AND** the manifest is not presented as a complete inventory of the deferred mode

#### Scenario: The platform cannot enumerate what it has no authority over

- **WHEN** an enumeration is attempted for a vault-custody mode without the owner's key authority
- **THEN** the platform reports the mode as unenumerable by it and defers to the owner's authority
- **AND** it does not synthesize an inventory from its own reference records

### Requirement: Export enumerates everything owned and states, per item, whether it is enclosed or retrievable elsewhere

An export SHALL enumerate every item the requesting principal owns or produced, including commons contributions, private content, preferences, ledger and settlement history, and derivation and lineage records. For each enumerated item the export SHALL either enclose its content or provide a resolvable retrieval descriptor naming the custody holder and the means of retrieval. The bundle SHALL carry a completeness statement listing every enumerated item that was not enclosed and why. An export SHALL NOT silently omit an item it could not retrieve, and SHALL NOT present a partial bundle as complete. Export SHALL be available without approval gating, subject only to a stated rate limit. Export SHALL be dispatched as an action under `read_graph` per the cross-capability handle invariant and SHALL NOT add an advertised MCP handle.

Where an enumerated item is a dataset asset owned by the `data-commons` capability, the export SHALL consume that capability's manifest, license, and retrieval contract as a **read and boundary dependency**: it SHALL carry the dataset's own manifest reference and retrieval descriptor, and SHALL NOT redefine dataset manifests, licensing, pricing, gating, or contributor provenance. A portability successor that includes dataset assets SHALL name `data-commons` in its dependencies.

#### Scenario: Enclosed and referenced items are both enumerated

- **WHEN** a principal owns items across more than one custody mode
- **THEN** the bundle encloses the content the platform can produce
- **AND** provides a resolvable retrieval descriptor for each item it cannot enclose

#### Scenario: Completeness is stated, not implied

- **WHEN** any enumerated item is not enclosed
- **THEN** the bundle's completeness statement lists that item and the reason
- **AND** the bundle is labelled partial

#### Scenario: Nothing is dropped silently

- **WHEN** retrieval of an owned item fails for any reason
- **THEN** the item still appears in the enumeration with its failure recorded
- **AND** the export does not report success as though the item did not exist

#### Scenario: Dataset assets defer to the data-commons contract

- **WHEN** an owned item is a dataset asset governed by `data-commons`
- **THEN** the export carries that capability's manifest reference and retrieval descriptor
- **AND** the export does not restate or override its licensing, pricing, gating, or contributor provenance

#### Scenario: Export adds no handle

- **WHEN** the connector's advertised tool list is inspected after export ships
- **THEN** no export handle appears
- **AND** export is reachable as an action under `read_graph`

### Requirement: Every supported custody mode must satisfy the export contract

A custody mode SHALL NOT be offered to users unless content held under it can be enumerated and retrieved by its owner through the export contract. Inability to export out of a custody mode SHALL be treated as a defect in that mode rather than as a limitation of export. Where a mode's conformance is incomplete, the system SHALL report that mode as non-conforming rather than reporting exports under it as complete, and SHALL NOT present it as a supported custody choice.

#### Scenario: A non-exportable mode is not offered

- **WHEN** a candidate custody mode cannot satisfy enumeration and retrieval for its owner
- **THEN** it is not presented as an available custody choice

#### Scenario: Partial conformance is reported honestly

- **WHEN** a supported mode's export conformance is incomplete
- **THEN** exports touching that mode are labelled partial with the gap named
- **AND** the mode is reported as non-conforming rather than covered

### Requirement: An unavailable custody holder yields a graceful resumable deferral

When content lives with a holder that is not currently reachable — including a host that is offline — the export SHALL return a graceful deferral for the affected items rather than failing the whole export or omitting them. The deferral SHALL identify the unreachable holder, SHALL be resumable so the same export can be completed when the holder returns without re-requesting the already-retrieved items, and SHALL be distinguishable from a permanent failure. The remainder of the export SHALL be delivered rather than withheld.

#### Scenario: Offline host defers rather than fails

- **WHEN** items live on a host that is not currently online
- **THEN** the export delivers everything else and marks those items deferred with the holder identified
- **AND** the response is an explicit unavailable-holder signal, not an error

#### Scenario: Resuming completes the same bundle

- **WHEN** the previously unreachable holder becomes available and the export is resumed
- **THEN** the deferred items are retrieved and added to the same export
- **AND** already-retrieved items are not fetched again

#### Scenario: Permanent failure is distinguishable from deferral

- **WHEN** an item cannot be retrieved because it no longer exists at its holder
- **THEN** it is recorded as permanently unavailable rather than deferred

### Requirement: An export contains only the requesting principal's own private content

An export SHALL NOT include private content belonging to another principal, in any custody mode, even where the requester has authorized access to a containing artifact, is a collaborator on it, or holds an elevated platform role. The same visibility and ownership predicate that governs reads SHALL govern export assembly, and SHALL be applied to derived and embedded material as well as to whole items. An export SHALL NOT reveal the existence of another principal's private content through references, counts, or manifest entries.

#### Scenario: Shared artifact does not export another's private layer

- **WHEN** the requester exports an artifact they collaborate on that contains another principal's private content
- **THEN** the export includes the requester's own layer and the shared layer
- **AND** the other principal's private content is absent, including from manifests and counts

#### Scenario: Elevated role grants no export reach

- **WHEN** a principal holding an elevated platform role exports their own data
- **THEN** the export contains only what they own as a principal
- **AND** their role grants no additional content

### Requirement: Deletion erases platform-held content directly and issues a verifiable obligation to every other holder

Account deletion SHALL directly and permanently erase the content the platform holds for the deleting principal, within a stated bounded window, and SHALL emit a per-item erasure record. Deletion SHALL be dispatched as an action under `write_graph` per the cross-capability handle invariant and SHALL NOT add an advertised MCP handle. For content under any other custody mode, the system SHALL issue a deletion obligation to the recorded holder, SHALL record whether that obligation was acknowledged and discharged, and SHALL report each such item as confirmed or unconfirmed. The system SHALL NOT report an item as deleted on the basis of having issued an obligation. A deletion summary SHALL distinguish erased, confirmed-by-holder, and unconfirmed items, and unconfirmed items SHALL remain available to the principal so they can pursue the holder directly.

Erasure records and holder obligations SHALL be **custody-mode-scoped**: one obligation and one discharge record per holder, each naming the holder and its mode, with no aggregate claim that outruns the per-holder records. Because the deleting principal's account identity does not survive deletion, the post-deletion summary SHALL NOT be retrievable by authenticating as the deleted principal. It SHALL instead be issued at confirmation time as (a) a self-contained receipt document delivered to the principal, listing each item, its holder, its mode, and its confirmed or unconfirmed state, which remains readable with no platform involvement at all; and (b) a bearer capability the principal holds, which resolves the current confirmation state of those obligations without resolving, requiring, or revealing the deleted identity. The capability's server-side record SHALL contain only what the lookup needs — item and holder references and their obligation state — and SHALL NOT retain the principal's identifying data to serve it. The capability SHALL expire under a stated policy, and its expiry SHALL NOT invalidate the self-contained receipt document.

#### Scenario: Platform-held content is erased and recorded

- **WHEN** deletion proceeds for content the platform holds
- **THEN** the content is permanently erased within the stated window
- **AND** a per-item erasure record is written

#### Scenario: Obligation is not evidence of erasure

- **WHEN** a deletion obligation is issued to a non-platform holder and no discharge is recorded
- **THEN** that item is reported as unconfirmed
- **AND** it is not counted as deleted in any summary shown to the principal

#### Scenario: The principal can see what remains unconfirmed

- **WHEN** deletion completes with some obligations undischarged
- **THEN** the summary lists those items with their holder and custody mode
- **AND** the principal holds a self-contained receipt document listing them that needs no platform call to read

#### Scenario: Post-deletion state resolves without the deleted identity

- **WHEN** the principal checks whether an outstanding obligation has since been discharged
- **THEN** the bearer capability issued at confirmation resolves the obligation state
- **AND** it does not require authenticating as the deleted principal, and does not resolve or reveal that identity

#### Scenario: The capability record retains no identity

- **WHEN** the capability's server-side record is inspected
- **THEN** it contains only item and holder references and their obligation state
- **AND** it contains no identifying data for the deleted principal

### Requirement: Commons contributions survive deletion with identity detached and derivatives are never cascaded

Deletion SHALL NOT remove the principal's public commons contributions, and SHALL NOT delete, hide, or break artifacts derived from them. Deleted-principal contributions SHALL remain readable with their authoring identity detached and presented as anonymous. Lineage and derivation edges SHALL be preserved so that derivative artifacts continue to resolve their provenance, terminating at an anonymous ancestor. Content-level attribution requirements SHALL NOT be used to justify retaining the identity after deletion.

#### Scenario: Derivatives keep working

- **WHEN** a principal whose contribution has derivatives deletes their account
- **THEN** every derivative remains readable and functional
- **AND** its provenance chain resolves, terminating at an anonymous ancestor

#### Scenario: Contribution stays, identity goes

- **WHEN** deletion completes
- **THEN** the principal's public commons contributions remain readable
- **AND** they present as anonymous with no residual identifying authorship

#### Scenario: No cascade deletion

- **WHEN** deletion is requested
- **THEN** no artifact authored by another principal is deleted or hidden as a consequence

### Requirement: Identity detachment over append-only records is resolution-time suppression, not rewriting

Where a principal's identifier appears in an append-only record — contribution ledgers, attribution edges, moderation decisions, settlement history — deletion SHALL NOT rewrite or remove those rows. Deletion SHALL write an authoritative detachment marker for the principal, and every identity resolution path SHALL consult it and return the anonymized principal instead of the original identity. Any surface that resolves a principal identifier SHALL honor the marker, including exports, projections, discovery signals, audit views, and external mirrors regenerated after detachment. A surface that cannot honor the marker SHALL NOT resolve the identifier at all.

#### Scenario: Ledger rows persist while identity resolves anonymized

- **WHEN** a principal with append-only ledger history is deleted
- **THEN** the ledger rows remain intact and countable
- **AND** every resolution of that principal's identifier returns the anonymized principal

#### Scenario: Detachment reaches every resolving surface

- **WHEN** any surface resolves a detached principal identifier after deletion
- **THEN** it returns the anonymized principal rather than the original identity

#### Scenario: A non-honoring surface withholds rather than leaks

- **WHEN** a surface cannot consult the detachment marker
- **THEN** it omits the principal identifier entirely rather than resolving it to the original identity

### Requirement: Deletion is explicitly confirmed, initiator-bound, bounded in time, and irreversible from the platform side

Deletion SHALL require an explicit confirmation step bound to the account holder, SHALL NOT be completable by another principal on their behalf, and SHALL NOT be triggerable by a single unauthenticated or replayable request. The confirmation request SHALL be dispatched as an action under `write_graph` per the cross-capability handle invariant and SHALL NOT add an advertised MCP handle. The confirmation SHALL expire within a stated window. Once confirmed, deletion SHALL proceed to completion without further action by the principal, and the platform SHALL NOT offer recovery of erased content. The irreversibility and the existence of unconfirmed non-platform items SHALL be stated to the principal before confirmation, and the principal SHALL be told that exporting first is the only way to retain their data.

#### Scenario: Third party cannot delete an account

- **WHEN** a principal other than the account holder attempts to initiate or confirm deletion
- **THEN** the attempt is refused and no deletion state is created

#### Scenario: Confirmation expires

- **WHEN** the confirmation is not completed within the stated window
- **THEN** it becomes invalid and deletion does not proceed
- **AND** a replay of the expired confirmation is refused

#### Scenario: Consequences are stated before the irreversible step

- **WHEN** the principal reaches the confirmation step
- **THEN** they are told that erasure is irreversible, that export is the only way to retain data, and that items under other custody may remain unconfirmed

#### Scenario: Deletion and confirmation add no handle

- **WHEN** the connector's advertised tool list is inspected after deletion ships
- **THEN** no deletion or confirmation handle appears
- **AND** both are reachable as actions under `write_graph`
