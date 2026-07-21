"""Tiny, dependency-FREE core for reserved reference-design identity.

Codex r21 #2: the central reserved-seed WRITE GUARD (daemon_server) must be able
to answer "is this a reserved id?" and "is this the reserved author?" WITHOUT
importing the whole ``branch_designs`` package. That package parses on-disk
artifact JSON and pulls in heavy deps; importing it on every branch write meant a
broken/optional seed package raised on import and the guard fail-closed-refused
EVERY id — taking ordinary create/update/delete/fork/import offline (a Forever
Rule violation: an optional-seed failure must not disable unrelated uptime
surfaces).

This module has NO dependency beyond the stdlib (``hashlib``): the reserved-id
predicate + author sanitizer are pure functions over a STATIC manifest. It cannot
fail to import because of a broken artifact, so the guard always has a real
protected-id set (fail-closed FOR RESERVED IDS specifically) while ordinary
non-reserved writes proceed. ``branch_designs`` re-exports these as the single
source of truth.
"""
from __future__ import annotations

import hashlib

# The reserved system author. NOT a design tag (tags are user-forgeable); the
# author is the ownership signal that build/fork/import paths strip.
RESERVED_SEED_AUTHOR = "reference-designs"

# STATIC manifest of packaged reference designs as (design_id, design_version).
# Artifact-parse-INDEPENDENT source of truth: the guard derives reserved ids from
# THIS via hashlib, never by parsing the artifact JSON (Codex r18 #2). Keep in
# sync with the on-disk artifacts; ``test_packaged_manifest_matches_on_disk_artifacts``
# cross-checks the two so a version bump that forgets this manifest trips a test.
PACKAGED_DESIGN_MANIFEST: frozenset[tuple[str, int]] = frozenset({
    ("patch_loop_reference", 1),
})

# Packaging + HEALTH invariant: the design_ids the package MUST ship. Derived
# from the manifest so the two can never drift.
PACKAGED_DESIGN_IDS = frozenset(design_id for design_id, _v in PACKAGED_DESIGN_MANIFEST)


def reference_branch_id(design_id: str, design_version: int) -> str:
    """Deterministic, RESERVED branch_def_id for a seeded reference design.

    Unspoofable: ``branch_def_id`` is server-assigned on every build/fork (users
    cannot set it), so a user can never occupy this id. Same 12-hex shape as
    ``_new_id`` so it round-trips every id-shaped consumer.
    """
    digest = hashlib.sha256(
        f"tinyassets.reference-design:{design_id}@v{int(design_version)}".encode()
    ).hexdigest()
    return digest[:12]


def reserved_seed_ids() -> frozenset[str]:
    """The deterministic reserved branch_def_ids of ALL packaged reference
    designs, computed from the STATIC manifest via hashlib — NEVER by parsing the
    artifact JSON (Codex r18 #2 fail-open fix). A pure hash over a static
    frozenset cannot fail or return empty, so the write guard always has a real
    protected-id set. Forgery-immune (server-assigned ids)."""
    return frozenset(
        reference_branch_id(design_id, version)
        for design_id, version in PACKAGED_DESIGN_MANIFEST
    )


def is_reserved_seed_id(branch_def_id: str) -> bool:
    """True if ``branch_def_id`` is the reserved id of a packaged reference
    design. The single, import-light, parse-independent predicate the storage
    write guard uses to protect the seed against EVERY public writer (Codex r17
    #3 / r18 #2 / r21 #2)."""
    return bool(branch_def_id) and branch_def_id in reserved_seed_ids()


def sanitize_reserved_author(author: str | None) -> str:
    """Strip the reserved seed author from a user-supplied value so it cannot be
    smuggled onto a user branch via build/fork/import. Returns "" when the value
    is the reserved author, else the value unchanged. Defensive against
    non-strings: never ``.strip()`` a non-string (returns "")."""
    if not isinstance(author, str):
        return ""
    return "" if author.strip() == RESERVED_SEED_AUTHOR else author
