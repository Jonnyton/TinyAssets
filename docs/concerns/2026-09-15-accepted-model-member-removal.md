# Removing an unavailable accepted model source needs owner reconsent

September15,2026: Fable reconnect shape review79934 identified that
tinyassets/api/model_access_requests.py::capture_action requires every previous
member to remain in a proposed manifest. Reverified in source before reconnect
implementation. Reconnect can preserve a ready independent member by refusing a
destructive republish, but cannot safely drop an unavailable accepted source.
Restoring that source is not always what the owner wants or can do.

Needed: explicit owner-driven removal/reconsent using existing model-access
authority, preserving unrelated scope, cost ceilings and private agent content.
Design the change before implementation; do not silently reduce membership,
reactivate a revoked grant or reset to legacy provider-only serving. Test current
home/owner/CAS and removal of the root as well as another member. This is not
part of the credential-renewal patch and remains unresolved.
