"""Tests for the scene commit packet schema and emission."""

from __future__ import annotations

import json

from tinyassets.packets import (
    EditorialVerdict,
    FactRef,
    PromiseRef,
    RelationshipDelta,
    ScenePacket,
    WorldStateDelta,
)


class TestFactRef:
    def test_defaults(self):
        f = FactRef(fact_id="f1", text="Ryn is a scout", source_type="narrator_claim")
        assert f.confidence == 0.5
        assert f.importance == 0.5


class TestPromiseRef:
    def test_fields(self):
        p = PromiseRef(
            promise_type="foreshadowing",
            trigger_text="the locked door",
            context="Ryn noticed the locked door at the end of the corridor.",
            scene_id="s1",
            chapter_number=1,
        )
        assert p.promise_type == "foreshadowing"
        assert p.importance == 0.5


class TestRelationshipDelta:
    def test_fields(self):
        r = RelationshipDelta(
            source="ryn", target="kael",
            relation_type="alliance", delta_type="strengthened",
        )
        assert r.delta_type == "strengthened"


class TestWorldStateDelta:
    def test_fields(self):
        d = WorldStateDelta(
            entity_id="ryn",
            field_name="location",
            old_value="northern_gate",
            new_value="ashwater_market",
        )
        assert d.old_value == "northern_gate"


class TestEditorialVerdict:
    def test_defaults(self):
        v = EditorialVerdict(
            verdict="accept",
            structural_pass=True,
            structural_score=0.85,
            hard_failure=False,
        )
        assert v.concerns == []
        assert v.protect == []


class TestScenePacket:
    def test_minimal_packet(self):
        p = ScenePacket(
            scene_id="test-B1-C1-S1",
            universe_id="test",
            book_number=1,
            chapter_number=1,
            scene_number=1,
        )
        assert p.scene_id == "test-B1-C1-S1"
        assert p.facts_introduced == []
        assert p.promises_opened == []
        assert p.word_count == 0

    def test_full_packet(self):
        p = ScenePacket(
            scene_id="sporemarch-B1-C1-S1",
            universe_id="sporemarch",
            book_number=1,
            chapter_number=1,
            scene_number=1,
            pov_character="Ryn",
            location="Northern Gate",
            participants=["Ryn", "Kael"],
            facts_introduced=[
                FactRef(
                    fact_id="f1",
                    text="Ryn guards the gate",
                    source_type="narrator_claim",
                ),
            ],
            promises_opened=[
                PromiseRef(
                    promise_type="foreshadowing",
                    trigger_text="locked door",
                    context="A locked door at the corridor's end.",
                    scene_id="sporemarch-B1-C1-S1",
                    chapter_number=1,
                ),
            ],
            editorial=EditorialVerdict(
                verdict="accept",
                structural_pass=True,
                structural_score=0.9,
                hard_failure=False,
            ),
            word_count=1200,
        )
        assert len(p.facts_introduced) == 1
        assert len(p.promises_opened) == 1
        assert p.editorial is not None
        assert p.editorial.verdict == "accept"

    def test_to_dict(self):
        p = ScenePacket(
            scene_id="test-B1-C1-S1",
            universe_id="test",
            book_number=1,
            chapter_number=1,
            scene_number=1,
            word_count=500,
        )
        d = p.to_dict()
        assert isinstance(d, dict)
        assert d["scene_id"] == "test-B1-C1-S1"
        assert d["word_count"] == 500
        assert isinstance(d["facts_introduced"], list)

    def test_to_dict_with_nested(self):
        p = ScenePacket(
            scene_id="s1",
            universe_id="u1",
            book_number=1,
            chapter_number=1,
            scene_number=1,
            facts_introduced=[
                FactRef(fact_id="f1", text="test", source_type="narrator_claim"),
            ],
            editorial=EditorialVerdict(
                verdict="accept",
                structural_pass=True,
                structural_score=0.8,
                hard_failure=False,
                concerns=[{"text": "minor pacing issue"}],
            ),
        )
        d = p.to_dict()
        assert d["facts_introduced"][0]["fact_id"] == "f1"
        assert d["editorial"]["verdict"] == "accept"
        assert len(d["editorial"]["concerns"]) == 1

    def test_to_dict_is_json_serializable(self):
        import json

        p = ScenePacket(
            scene_id="s1",
            universe_id="u1",
            book_number=1,
            chapter_number=1,
            scene_number=1,
            relationship_deltas=[
                RelationshipDelta(
                    source="ryn", target="kael",
                    relation_type="ally", delta_type="introduced",
                ),
            ],
            world_state_deltas=[
                WorldStateDelta(
                    entity_id="ryn", field_name="location",
                    old_value=None, new_value="gate",
                ),
            ],
        )
        # Should not raise
        serialized = json.dumps(p.to_dict())
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["relationship_deltas"][0]["source"] == "ryn"


class TestEmitScenePacket:
    """Tests for _emit_scene_packet writing packet JSON alongside prose."""

    def test_emits_packet_file(self, tmp_path):
        """Accepted scene should produce a .packet.json file."""
        from domains.fantasy_daemon.phases.commit import _emit_scene_packet
        from tinyassets.evaluation.structural import StructuralResult

        # Use dict-style characters (as orient actually produces them)
        # to verify participants are extracted as plain strings.
        state = {
            "_universe_path": str(tmp_path),
            "universe_id": "test-universe",
            "book_number": 1,
            "chapter_number": 1,
            "scene_number": 1,
            "orient_result": {
                "pov_character": "Loral",
                "characters": [
                    {"name": "Loral", "character_id": "loral", "id": "loral"},
                    {"name": "Myra", "character_id": "myra", "id": "myra"},
                ],
                "location": "Underhallow",
            },
        }
        structural = StructuralResult(
            checks=[], aggregate_score=0.85,
            hard_failure=False, violations=[],
        )
        _emit_scene_packet(
            state=state,
            scene_id="test-B1-C1-S1",
            facts_list=[],
            promises=[],
            structural=structural,
            editorial=None,
            verdict="accept",
            word_count=1200,
            is_revision=False,
            worldbuild_signals=[],
        )

        packet_file = (
            tmp_path / "output" / "book-1" / "chapter-01" / "scene-01.packet.json"
        )
        assert packet_file.exists()

        data = json.loads(packet_file.read_text(encoding="utf-8"))
        assert data["scene_id"] == "test-B1-C1-S1"
        assert data["universe_id"] == "test-universe"
        assert data["pov_character"] == "Loral"
        assert data["word_count"] == 1200
        # participants must be plain strings, not dicts
        assert data["participants"] == ["Loral", "Myra"]
        for p in data["participants"]:
            assert isinstance(p, str)
        assert data["editorial"]["verdict"] == "accept"
        assert data["editorial"]["structural_score"] == 0.85

    def test_emits_with_facts_and_promises(self, tmp_path):
        """Packet should include extracted facts and promises."""
        from domains.fantasy_daemon.phases.commit import _emit_scene_packet
        from tinyassets.evaluation.structural import StructuralResult
        from tinyassets.knowledge.models import FactWithContext, SourceType

        facts = [
            FactWithContext(
                fact_id="f1",
                text="Loral is a mycologist",
                source_type=SourceType.AUTHOR_FACT,
                importance=0.8,
            ),
        ]
        promises = [
            {
                "promise_type": "foreshadowing",
                "trigger_text": "the sealed chamber",
                "context": "A sealed chamber beneath the Underhallow.",
                "importance": 0.7,
            },
        ]
        state = {
            "_universe_path": str(tmp_path),
            "universe_id": "test",
            "book_number": 1,
            "chapter_number": 2,
            "scene_number": 3,
            "orient_result": {},
        }
        structural = StructuralResult(
            checks=[], aggregate_score=0.9,
            hard_failure=False, violations=[],
        )
        _emit_scene_packet(
            state=state,
            scene_id="test-B1-C2-S3",
            facts_list=facts,
            promises=promises,
            structural=structural,
            editorial=None,
            verdict="accept",
            word_count=800,
            is_revision=False,
            worldbuild_signals=[],
        )

        packet_file = (
            tmp_path / "output" / "book-1" / "chapter-02" / "scene-03.packet.json"
        )
        assert packet_file.exists()
        data = json.loads(packet_file.read_text(encoding="utf-8"))
        assert len(data["facts_introduced"]) == 1
        assert data["facts_introduced"][0]["text"] == "Loral is a mycologist"
        # source_type must serialize as the enum value string, not repr
        assert data["facts_introduced"][0]["source_type"] == "author_fact"
        assert "SourceType" not in data["facts_introduced"][0]["source_type"]
        assert len(data["promises_opened"]) == 1
        assert data["promises_opened"][0]["promise_type"] == "foreshadowing"

    def test_no_universe_path_skips(self):
        """Missing _universe_path should silently skip emission."""
        from domains.fantasy_daemon.phases.commit import _emit_scene_packet
        from tinyassets.evaluation.structural import StructuralResult

        state = {"orient_result": {}}
        structural = StructuralResult(
            checks=[], aggregate_score=0.5,
            hard_failure=False, violations=[],
        )
        # Should not raise
        _emit_scene_packet(
            state=state,
            scene_id="x",
            facts_list=[],
            promises=[],
            structural=structural,
            editorial=None,
            verdict="accept",
            word_count=0,
            is_revision=False,
            worldbuild_signals=[],
        )
