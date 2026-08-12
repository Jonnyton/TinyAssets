## REMOVED Requirements

### Requirement: The current host pool uses REST registration and heartbeat state
**Reason**: The provider-shaped host-pool client is part of the retired fleet model and is not the serving-binding credential authority.
**Migration**: User credentials live in the universe vault and workflows bind directly to them; future requester-host discovery must use that authority model rather than resurrecting this client.

### Requirement: Current bid discovery is polling-only and does not claim work
**Reason**: The bid poller is coupled to the deleted host-pool package and does not execute through serving bindings.
**Migration**: Preserve paid-market queue records independently; any future matcher must produce an explicit workflow credential binding before execution.
