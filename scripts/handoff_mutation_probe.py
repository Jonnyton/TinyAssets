"""Prove the real-world handoff tests go red when an invariant is removed.

Each mutation is temporary and the exact original bytes are restored in a
``finally`` block. No git restore/reset operation is used, so unrelated dirty
work is never touched.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE_TEST = "tests/test_handoff_store.py"
AUTHORITY_TEST = "tests/test_handoff_authority.py"
RECEIPTS_TEST = "tests/test_handoff_receipts.py"
CONCURRENCY_TEST = "tests/test_handoff_concurrency.py"
OUTCOMES_TEST = "tests/test_outcome_events.py"

MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "outcome-schema-owner",
        "tinyassets/outcomes/schema.py",
        "conn.executescript(OUTCOME_SCHEMA + OUTCOME_EVIDENCE_SCHEMA)",
        "conn.executescript(OUTCOME_SCHEMA)",
        [
            f"{STORE_TEST}::"
            "test_outcome_schema_owner_creates_evidence_lifecycle_tables"
        ],
    ),
    (
        "handoff-owner-scope",
        "tinyassets/handoffs/store.py",
        '"SELECT * FROM handoff WHERE handoff_id = ? AND owner_id = ?",',
        '"SELECT * FROM handoff WHERE handoff_id = ? OR owner_id = ?",',
        [
            f"{STORE_TEST}::"
            "test_handoff_store_scopes_reads_and_deduplicates_effect_identity"
        ],
    ),
    (
        "handoff-effect-dedup",
        "tinyassets/handoffs/store.py",
        "    UNIQUE (effect_key, sink),\n",
        "    UNIQUE (handoff_id, sink),\n",
        [
            f"{STORE_TEST}::"
            "test_handoff_store_scopes_reads_and_deduplicates_effect_identity"
        ],
    ),
    (
        "handoff-transition-cas",
        "tinyassets/handoffs/store.py",
        "WHERE handoff_id = ? AND owner_id = ? AND state = ?",
        "WHERE handoff_id = ? AND owner_id = ? AND state <> ?",
        [
            f"{STORE_TEST}::"
            "test_handoff_store_appends_compare_and_swap_transitions"
        ],
    ),
    # ── Authority ─────────────────────────────────────────────────────────
    (
        "subject-anonymous-allowed",
        "tinyassets/handoffs/authority.py",
        'if not subject or subject == "anonymous":',
        "if False:",
        [f"{AUTHORITY_TEST}::TestRequestSubject"],
    ),
    (
        "source-owner-check",
        "tinyassets/handoffs/authority.py",
        "if not owner or owner != subject:",
        "if False:",
        [f"{AUTHORITY_TEST}::TestSourceAuthority::test_foreign_run_is_refused"],
    ),
    (
        "outcome-run-owner-check",
        "tinyassets/api/extensions.py",
        'if owner in ("", "anonymous") or owner != actor_id:',
        "if False:",
        [
            f"{OUTCOMES_TEST}::TestSingleRegistry::"
            "test_record_outcome_requires_authenticated_run_ownership"
        ],
    ),
    (
        "declared-destination-substitution",
        "tinyassets/handoffs/models.py",
        "if supplied and supplied != declaration.destination:",
        "if False:",
        [f"{AUTHORITY_TEST}::TestDeclarationBinding"],
    ),
    (
        "soul-effect-authority",
        "tinyassets/handoffs/authority.py",
        "    if decision == DENIED:",
        "    if False:",
        [
            f"{AUTHORITY_TEST}::TestDestinationConsent::"
            "test_a_soul_denied_destination_is_refused_even_with_consent"
        ],
    ),
    (
        "destination-consent",
        "tinyassets/handoffs/authority.py",
        "if not is_consent_active(universe_dir, sink=sink, destination=destination):",
        "if False:",
        [f"{AUTHORITY_TEST}::TestDestinationConsent"],
    ),
    (
        "irreversible-confirmation",
        "tinyassets/handoffs/service.py",
        "if declaration.irreversible:\n        fingerprint = confirmation_fingerprint(",
        "if False:\n        fingerprint = confirmation_fingerprint(",
        [f"{AUTHORITY_TEST}::TestConfirmation"],
    ),
    (
        "confirmation-single-use",
        "tinyassets/handoffs/store.py",
        "AND consumed_at IS NULL AND expires_at > ?",
        "AND expires_at > ?",
        [
            f"{AUTHORITY_TEST}::TestConfirmation::"
            "test_confirmation_is_single_use"
        ],
    ),
    (
        # The stale-version refusal is enforced by TWO redundant bindings in the
        # consume WHERE clause: effect_key (which derives from the source version
        # and content hash) and fingerprint (which contains effect_key again).
        # Mutating either one alone stays green — the probe found that twice —
        # so the honest mutation neutralises both and proves the pair is what
        # rejects a token minted against an earlier version.
        "confirmation-binds-source-version",
        "tinyassets/handoffs/store.py",
        "WHERE token = ? AND owner_id = ? AND effect_key = ?\n"
        "                   AND sink = ? AND fingerprint = ?",
        "WHERE token = ? AND owner_id = ? AND ? IS NOT NULL\n"
        "                   AND sink = ? AND ? IS NOT NULL",
        [
            f"{AUTHORITY_TEST}::TestConfirmation::"
            "test_confirmation_bound_to_a_stale_source_version_does_not_match"
        ],
    ),
    (
        "credential-blindness",
        "tinyassets/handoffs/models.py",
        "if str(key).strip().lower() in _CREDENTIAL_KEYS:",
        "if False:",
        [
            f"{AUTHORITY_TEST}::TestDeclarationBinding::"
            "test_declaration_carrying_credential_material_is_refused"
        ],
    ),
    (
        "adapter-fails-closed",
        "tinyassets/handoffs/adapters.py",
        "if adapter is None:",
        "if False:",
        [f"{AUTHORITY_TEST}::TestAdapterSeam::test_unregistered_adapter_fails_closed"],
    ),
    (
        "accepted-needs-external-id",
        "tinyassets/handoffs/adapters.py",
        'if self.state == "accepted" and not (self.external_id or "").strip():',
        "if False:",
        [
            f"{AUTHORITY_TEST}::TestAdapterSeam::"
            "test_accepted_without_an_external_id_is_rejected"
        ],
    ),
    (
        "handoff-write-scope",
        "tinyassets/handoffs/service.py",
        '_HANDOFF_WRITE_ACTIONS: frozenset[str] = frozenset({\n    "handoff_prepare",',
        '_HANDOFF_WRITE_ACTIONS: frozenset[str] = frozenset({\n    "unused_placeholder",',
        [
            f"{AUTHORITY_TEST}::TestRouterHalf::"
            "test_scope_registry_derives_write_and_costly"
        ],
    ),
    # ── Receipts ──────────────────────────────────────────────────────────
    (
        "dry-run-purity",
        "tinyassets/handoffs/service.py",
        "    return {\n        \"would_handoff\": request.redacted(),",
        "    resolve_adapter(declaration.adapter)(request)\n"
        "    return {\n        \"would_handoff\": request.redacted(),",
        [f"{RECEIPTS_TEST}::TestDryRun"],
    ),
    (
        "exactly-once-boundary",
        "tinyassets/handoffs/service.py",
        "        effect = execute_replay_safe_effect(",
        "        _invoke()\n        effect = execute_replay_safe_effect(",
        [f"{RECEIPTS_TEST}::TestExactlyOnce"],
    ),
    (
        "adapter-state-nesting",
        "tinyassets/handoffs/service.py",
        'adapter_reply = effect.get("result")',
        'adapter_reply = effect.get("adapter_reply_that_does_not_exist")',
        [f"{RECEIPTS_TEST}::TestLifecycleSeparation"],
    ),
    (
        "submitted-is-not-accepted",
        "tinyassets/handoffs/service.py",
        'target = "accepted" if adapter_state == "accepted" else "submitted"',
        'target = "accepted" if adapter_state else "submitted"',
        [
            f"{RECEIPTS_TEST}::TestLifecycleSeparation::"
            "test_transport_success_proves_submission_only"
        ],
    ),
    (
        "owner-cannot-inflate",
        "tinyassets/handoffs/service.py",
        "if target not in _OWNER_TRANSITIONS:",
        "if False:",
        [
            f"{RECEIPTS_TEST}::TestLifecycleSeparation::"
            "test_owner_cannot_declare_its_own_handoff_accepted"
        ],
    ),
    (
        "identity-includes-destination",
        "tinyassets/handoffs/models.py",
        '"destination": destination.strip(),\n        }).encode("utf-8")',
        '}).encode("utf-8")',
        [f"{RECEIPTS_TEST}::TestEffectIdentity"],
    ),
    # ── Concurrency ───────────────────────────────────────────────────────
    (
        "concurrent-duplicate-suppression",
        "tinyassets/handoffs/service.py",
        "    except RuntimeError:\n        shared = _shared_pending(",
        "    except RuntimeError:\n        _invoke()\n        shared = _shared_pending(",
        [f"{CONCURRENCY_TEST}::TestDuplicateConcurrentSubmissions"],
    ),
    # ── Outcome registry ──────────────────────────────────────────────────
    (
        "attestation-is-not-verified",
        "tinyassets/handoffs/service.py",
        'evidence_level="user_attested",\n        run_id=run_id,',
        'evidence_level="externally_verified",\n        run_id=run_id,',
        [f"{OUTCOMES_TEST}::TestEvidenceLevels"],
    ),
    (
        "evidence-transition-legality",
        "tinyassets/handoffs/models.py",
        "if to_level not in LEGAL_EVIDENCE_TRANSITIONS[from_level]:",
        "if False:",
        [
            f"{OUTCOMES_TEST}::TestEvidenceLevels::"
            "test_an_illegal_evidence_transition_is_refused"
        ],
    ),
    (
        "artifact-dedup",
        "tinyassets/handoffs/models.py",
        '    raw = raw.rstrip("/")\n    return f"{kind}:{raw}"',
        '    return f"{kind}:{raw}"',
        [f"{OUTCOMES_TEST}::TestMultiSourceAttribution"],
    ),
    (
        "attestation-preserves-attester",
        "tinyassets/handoffs/store.py",
        "                   SET evidence_level = ?, evidence_source = ?, updated_at = ?,",
        "                   SET evidence_level = ?, evidence_source = ?, updated_at = ?,\n"
        "                       attested_by = 'overwritten',",
        [
            f"{OUTCOMES_TEST}::TestEvidenceLevels::"
            "test_verification_preserves_the_original_attester"
        ],
    ),
    (
        "legacy-rows-stay-unattributed",
        "tinyassets/outcomes/schema.py",
        "            outcome_id, '', run_id, outcome_type, 'legacy_outcome_event',",
        "            outcome_id, COALESCE(verified_by, ''), run_id, outcome_type, "
        "'legacy_outcome_event',",
        [f"{OUTCOMES_TEST}::TestSingleRegistry"],
    ),
    (
        # "What if someone wired the two lifecycles together?" — the inert
        # first attempt (adding an unused method) stayed green and proved
        # nothing, so this mutation makes an outcome transition actually reach
        # into gate_event.
        "gate-events-stay-separate",
        "tinyassets/handoffs/store.py",
        "                    canonical_json(evidence or {}), stamp,\n"
        "                ),\n            )",
        "                    canonical_json(evidence or {}), stamp,\n"
        "                ),\n            )\n"
        "            conn.execute(\n"
        "                \"UPDATE gate_event SET verification_status = 'verified'\"\n"
        "            )",
        [f"{OUTCOMES_TEST}::TestGateEventSeparation"],
    ),
]


def _tests_go_red(tests: list[str]) -> bool:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-x",
            "-q",
            "-p",
            "no:randomly",
            *tests,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        for name, rel, *_ in MUTATIONS:
            print(f"{name:32s} {rel}")
        return 0

    selected = [
        mutation
        for mutation in MUTATIONS
        if not args.only or mutation[0] in args.only
    ]
    if not selected:
        print(f"no mutation matched {args.only}", file=sys.stderr)
        return 2

    findings: list[str] = []
    for name, rel, old, new, tests in selected:
        path = REPO / rel
        original = path.read_text(encoding="utf-8")
        if old not in original:
            findings.append(f"STALE ANCHOR: {name} ({rel})")
            print(f"[stale] {name}: anchor not found")
            continue
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        try:
            red = _tests_go_red(tests)
        finally:
            path.write_text(original, encoding="utf-8")
        if red:
            print(f"[ok] {name}: went red")
        else:
            findings.append(f"GREEN UNDER MUTATION: {name}")
            print(f"[finding] {name}: stayed green")

    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"every mutation went red ({len(selected)} checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
