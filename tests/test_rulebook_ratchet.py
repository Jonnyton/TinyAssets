"""The rulebook only shrinks.

`AGENTS.md` § *The rulebook only shrinks* states the rule; `scripts/check_context_budget.py`
pins every rulebook file at the byte size it had after the 2026-09-26 cut. This
file is the pawl: it proves the pins hold, that growth past a pin goes red, and
that lowering a pin is accepted.

Why a ratchet at all: the rule set grew from ~17.6 KB (2026-04-28) to 62,082 B
while the budget invariant was registered and violated the whole time, because
nothing failed. A measurement without something that fails is not a ratchet.

Bytes, not words or lines: bytes are what the model pays for, and one measure per
file avoids a second authority that can disagree with the first.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUDGET_SCRIPT = REPO_ROOT / "scripts" / "check_context_budget.py"

# The five files AGENTS.md names as the rulebook. Pinned here as well as in the
# script so that silently DROPPING a file from the pinned set — the cheapest way
# to escape a pin — fails too.
RULEBOOK = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/reference/quality-gates.md",
    "docs/reference/executable-gates.md",
    "docs/reference/delivery-flow.md",
)


def _load_budget_module():
    spec = importlib.util.spec_from_file_location("check_context_budget_ratchet", BUDGET_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cb():
    return _load_budget_module()


# ---------------------------------------------------------------- the pinned set


def test_every_rulebook_file_is_pinned(cb) -> None:
    pinned = {b.path for b in cb.CONFIG}
    assert pinned == set(RULEBOOK), (
        "the pinned set drifted from the rulebook AGENTS.md declares; dropping a "
        "file from CONFIG is the cheapest way to escape its pin"
    )


def test_pins_are_exact_not_round(cb) -> None:
    """A pin at a comfortable round number is a wish, not a ratchet."""
    for budget in cb.CONFIG:
        assert budget.max_bytes % 500 != 0, (
            f"{budget.path} is pinned at {budget.max_bytes}, a round number. Pin "
            "the achieved size instead."
        )


def test_line_caps_are_unchecked(cb) -> None:
    """Bytes are the ratchet; a reflow that cuts words must never fail on lines."""
    assert all(b.max_lines == 0 for b in cb.CONFIG)


# ------------------------------------------------------------------- the gate


def test_no_rulebook_file_exceeds_its_pin(cb) -> None:
    results, combined, hard_busted, _imported, missing = cb.run(REPO_ROOT)
    over = [f"{r.path}: {r.bytes} > {r.max_bytes}" for r in results if r.over_bytes]
    assert not over, "rulebook grew past its pin: " + "; ".join(over)
    assert not missing, f"a pinned rulebook file is gone: {missing}"
    assert combined <= cb.COMBINED_HARD_BYTES
    assert not hard_busted


def test_combined_ceiling_is_not_loose(cb) -> None:
    """The combined ceiling tracks the always-loaded files, not a wish.

    It must not exceed the sum of the always-loaded pins, or a file could grow
    inside a ceiling that never moves.
    """
    always = sum(b.max_bytes for b in cb.CONFIG if b.always_loaded)
    assert cb.COMBINED_HARD_BYTES <= always


def test_agents_md_states_the_rule() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "The rulebook only shrinks" in text
    assert "a new rule must displace an old one" in text


# ------------------------------------------------------- can it actually fail?


def _fake_tree(root: Path, sizes: dict[str, int]) -> None:
    for rel, size in sizes.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)


def test_growth_past_a_pin_goes_red(cb, tmp_path: Path) -> None:
    sizes = {b.path: b.max_bytes for b in cb.CONFIG}
    grown = cb.CONFIG[-1].path          # a pointer-loaded file, the weaker half
    sizes[grown] += 1
    _fake_tree(tmp_path, sizes)

    results, _combined, hard_busted, _imported, _missing = cb.run(tmp_path)

    assert hard_busted, "one byte over a pin must fail"
    assert [r.path for r in results if r.over_bytes] == [grown]


def test_lowering_a_pin_is_accepted(cb, tmp_path: Path) -> None:
    """Shrinking is always allowed — that is the ratchet turning, not a violation."""
    _fake_tree(tmp_path, {b.path: b.max_bytes // 2 for b in cb.CONFIG})

    results, _combined, hard_busted, _imported, missing = cb.run(tmp_path)

    assert not hard_busted
    assert not missing
    assert not any(r.over for r in results)


def test_deleting_a_rulebook_file_goes_red(cb, tmp_path: Path) -> None:
    """Deleting AGENTS.md must never be the cheapest way to satisfy its own pin."""
    sizes = {b.path: b.max_bytes for b in cb.CONFIG}
    sizes.pop("AGENTS.md")
    _fake_tree(tmp_path, sizes)

    _results, _combined, hard_busted, _imported, missing = cb.run(tmp_path)

    assert missing == ["AGENTS.md"]
    assert hard_busted


def test_pointer_files_do_not_count_toward_the_always_loaded_total(cb, tmp_path: Path) -> None:
    """A docs/reference procedure is pinned, but it is not paid for every turn.

    Folding it into COMBINED would make the per-turn payload read ~11 KB heavier
    than it is, and would push the combined total over its ceiling on a tree that
    is exactly at every pin.
    """
    _fake_tree(tmp_path, {b.path: b.max_bytes for b in cb.CONFIG})

    _results, combined, hard_busted, _imported, _missing = cb.run(tmp_path)

    always = sum(b.max_bytes for b in cb.CONFIG if b.always_loaded)
    assert combined == always
    assert not hard_busted
