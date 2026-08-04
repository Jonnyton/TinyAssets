Reviewed `36d75dbc28f5182cf49c43aee060a58e3e9ab643` against `62ce277d77738d18a734f155410bc3245b775725`. No files were edited.

1. **Important: self-issued grants make caller-forged evidence authoritative.**  
   `tinyassets/conversation_custody.py:707-723` ships `_issue_operation_grant`, which accepts a publicly constructible evidence object and an arbitrary `live_check` callback without requiring an authority-owned capability. A probe using `live_check=lambda …: True` successfully created and deleted custody state at a self-asserted, unregistered path. Underscore naming is not an access boundary, and this contradicts the no-production-issuer/constructor requirement. The packaged mirror has the identical defect.

2. **Important: caller-controlled time defeats grant expiry and retention enforcement.**  
   `tinyassets/conversation_custody.py:726-770` evaluates validity against the caller’s `now`; every storage operation forwards that value. `tinyassets/storage/conversation_custody.py:1028-1054,1105-1120` also uses it to authorize retention deletion. An adversarial probe accepted a grant that expired in 2000 while the actual clock was 2026 by supplying a 2000 timestamp. A holder can similarly fast-forward retention checks and forge receipt times.

3. **Important: retention deletion trusts a corrupted duplicate instead of the canonical record.**  
   `tinyassets/storage/conversation_custody.py:955-977` validates only scope columns, while `:1105-1120` reads `retention_until` directly without checking it against `record_json`. Changing only that column from 2030 to 2020 allowed `retention_expired` deletion even though the canonical thread record still contained 2030. This violates immutable retention and fail-closed integrity, creating a data-loss path.

4. **Important: create/append tombstones retain forbidden conversation association.**  
   `tinyassets/storage/conversation_custody.py:1151-1160` clears request/result fields but writes `deleted_target_digest` into every create/append tombstone. The design at `design.md:292-317` requires conversation association to be cleared, leaving only operation kind and high-entropy key digest. The probe confirmed the stable target digest remains queryable, unnecessarily correlating prior mutation keys with the deleted conversation.

Verification:

- Custody tests: 66 passed in 8.67s.
- Ruff: passed.
- Strict OpenSpec validation: passed.
- Mirror parity: all 328 canonical files matched.
- Packaged modules imported from the isolated runtime.
- `git diff --check`: clean.
- Static search confirmed no current production consumer beyond canonical modules and mirrors; the exact-seven public handle test passed.
- Same-provider fallback used as disclosed after Claude CLI exit 1 with empty stderr.

REJECT