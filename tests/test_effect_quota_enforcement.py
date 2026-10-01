"""An owner's outbound work is never refused by an effect-rate quota."""
from tinyassets.effectors.outbound_boundary import execute_replay_safe_effect


def test_effects_are_unmetered_and_replays_still_fire_once(tmp_path):
    calls = []

    def invoke():
        calls.append(1)
        return {"status": "succeeded", "delivered": True}

    for i in range(105):
        for _ in range(2):
            result = execute_replay_safe_effect(
                universe_dir=tmp_path, effect_key=str(i), sink="test", run_id="run",
                invoke=invoke,
            )
            assert result["status"] == "succeeded"
    assert len(calls) == 105
