# Independent file-bridge shape approval

September23,2026 UTC. Codex lead independently read the complete509-line
Claude design, committed as036d1037 in codex/file-bridge-next at base1f121719.
Read current api/deliveries, delivery_runtime, capture publication/replay,
run-file binding predicates, receipt projection and scoped-reset table handling.

**AGREE / APPROVE the MVP architecture for implementation.** Copy into
receiver-owned custody before acceptance, publish under the existing ordered
platform/runs writers, then bind inside acceptance on the already inserted
receiver run. Use one connection-receiving publication hook; never a nested
writer callback. Keep original sender-side inputs for occurrence identity and
rewrite to receiver references only for receiver execution. Preserve existing
global/physical capacity ceilings; no invented per-user entitlement or new API.

Implementation constraints and acceptance tests (not another design-review round):

- Publication and final acceptance recheck current sender authority, trusted
  source run/binding, receiver/link generation and receiver authority under the
  existing lock order. Do not grant read access from envelope metadata alone.
- Accepted-occurrence replay may bypass current receiver-link revocation only
  as the existing no-new-work replay does; sender ownership/source checks remain.
  It must not copy bytes or re-execute an indeterminate started attempt.
- Adding a name to scoped_reset's known-table set is NOT a deletion algorithm.
  Its exact-schema/ownership fences remain authoritative. Implement and test the
  new table's real cleanup/reference handling without broad reset permission;
  sender erasure must not delete receiver bytes or leave the receiver unable to
  resolve its accepted input. No real account deletion is authorized.
- Keep lower-level and unsourced RPC refusal defaults fail-closed. Test actual
  intake and dispatch paths, not only reject_file_references in isolation.
- Preserve raw bytes, digest/size validation, field mapping and bundle order.
  Copy/allocation failure cannot leave an accepted delivery. Bind failure rolls
  back the acceptance transaction; durable orphan cleanup remains recoverable.
- Existing safety tests may pass on base: do not demand all negatives be red.
  Reproduce missing transfer capability red; mutation-check relevant guards.
  No local Docker/WSL startup. Descriptor and POSIX coverage require hosted Linux
  before release; a Windows skip is not a pass.

This is shape/basic-safety approval, not exact-head code approval or shipped
capability. Root will review the finished implementation independently; normal
CI, deployment, two-owner ordinary app acceptance and specification sync remain.
