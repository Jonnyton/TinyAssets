"""Dark execution-authority contracts with no production composition root.

Package initialization transfers the sealed mechanism capabilities exactly
once into reviewed adapter closures, then removes every bootstrap/installer
entry point.  No raw mint callable remains reachable as a module or package
global after import.
"""

from . import verified as _verified_module

_m1_capability, _m2_capability, _m3_capability, _auth_checker = (
    _verified_module._take_bootstrap_capabilities()
)
delattr(_verified_module, "_take_bootstrap_capabilities")

from . import records as _records_module  # noqa: E402

_records_module._install_verified_capabilities(
    _m1_capability,
    _auth_checker,
)
delattr(_records_module, "_install_verified_capabilities")
delattr(_records_module, "_authority_capabilities")

from . import blob_proof as _blob_module  # noqa: E402

_blob_module._install_verified_capabilities(
    _m2_capability,
    _auth_checker,
)
delattr(_blob_module, "_install_verified_capabilities")

from .records import (  # noqa: E402
    BlobReferenceV1,
    ExecutionCandidateV1,
    ExecutionCapsuleV1,
    ExecutionGrantV1,
    ExecutionRecord,
    ExecutionTerminalV1,
    FieldDisposition,
    RecordAuthorityError,
    RecordSigner,
    RecordVerifier,
    SignedExecutionRecord,
    SignedRecordContract,
    canonical_payload_bytes,
    record_contract_for,
)
from .verified import (  # noqa: E402
    VerificationMechanism,
    Verified,
)

del _auth_checker
del _blob_module
del _m1_capability
del _m2_capability
del _m3_capability
del _records_module
del _verified_module

__all__ = [
    "BlobReferenceV1",
    "ExecutionCandidateV1",
    "ExecutionCapsuleV1",
    "ExecutionGrantV1",
    "ExecutionRecord",
    "ExecutionTerminalV1",
    "FieldDisposition",
    "RecordAuthorityError",
    "RecordSigner",
    "RecordVerifier",
    "SignedExecutionRecord",
    "SignedRecordContract",
    "VerificationMechanism",
    "Verified",
    "canonical_payload_bytes",
    "record_contract_for",
]
