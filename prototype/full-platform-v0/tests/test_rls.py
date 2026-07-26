"""T2 — RLS strips private from non-owners; owners see everything."""

from __future__ import annotations

import json
import uuid

from conftest import as_user, stub_embedding


def _assume_fixture_app(db, user_id):
    with db.cursor() as cur:
        cur.execute("SET ROLE tinyassets_fixture_app")
    as_user(db, user_id)


def _create_alice_node(db, alice_id, visibility="public", with_private_field=True):
    nid = str(uuid.uuid4())
    concept = {
        "purpose": "invoice OCR",
        "example_company": "AcmeCorp",  # will be marked private per field_visibility
    }
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.nodes (node_id, slug, name, domain, owner_user_id, "
            "concept, concept_visibility, structural_hash, embedding) "
            "VALUES (%s, %s, 'Invoice', 'accounting', %s, %s::jsonb, %s, 'hash', %s)",
            (nid, f"invoice-{nid[:8]}", alice_id, json.dumps(concept),
             visibility, stub_embedding(1)),
        )
        if with_private_field:
            cur.execute(
                "INSERT INTO public.artifact_field_visibility "
                "(artifact_id, artifact_kind, field_path, visibility, decided_by) "
                "VALUES (%s, 'node', %s, 'private', 'chatbot')",
                (nid, "/example_company"),
            )
        db.commit()
    return nid


def test_owner_sees_all_fields(db, alice_id):
    nid = _create_alice_node(db, alice_id)
    _assume_fixture_app(db, alice_id)
    with db.cursor() as cur:
        cur.execute("SELECT concept FROM public.nodes WHERE node_id = %s", (nid,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["example_company"] == "AcmeCorp"


def test_non_owner_sees_public_node_stripped(db, alice_id, bob_id):
    # Alice creates a public node with a private field
    _create_alice_node(db, alice_id, visibility="public")

    # Bob queries via discover_nodes (which applies strip_private_fields)
    _assume_fixture_app(db, bob_id)
    with db.cursor() as cur:
        cur.execute(
            "SELECT public.discover_nodes(%s, %s::vector(16), NULL, NULL, NULL, 10, true)",
            ("invoice", stub_embedding(1)),
        )
        result = cur.fetchone()[0]

    candidates = result["candidates"]
    assert len(candidates) == 1
    returned_concept = candidates[0]["concept"]
    assert returned_concept.get("purpose") == "invoice OCR"
    assert "example_company" not in returned_concept, \
        f"private field leaked to non-owner: {returned_concept}"


def test_non_owner_cannot_see_private_visibility_node(db, alice_id, bob_id):
    _create_alice_node(db, alice_id, visibility="private", with_private_field=False)

    _assume_fixture_app(db, bob_id)
    with db.cursor() as cur:
        cur.execute(
            "SELECT public.discover_nodes(%s, %s::vector(16), NULL, NULL, NULL, 10, true)",
            ("invoice", stub_embedding(1)),
        )
        result = cur.fetchone()[0]

    assert result["candidates"] == [], \
        f"private node visible to non-owner: {result['candidates']}"
