## Design

`rebind_provider` accepts only the provider name. The actor and universe come
from the authenticated request. The server resolver supplies the new seed;
caller authority fields are ignored. If more than one matching binding exists,
the operation fails without mutation. Otherwise the existing binding is
compare-and-swap revoked and the current enrollment is issued.
