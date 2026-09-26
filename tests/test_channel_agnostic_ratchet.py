"""The platform must not know what GitHub is.

Founder, 2026-09-03: *"must also be all agnostic shapes. no github spasific code
should excist on the plateform, nor should any other spasific channel code
excist. users can build what they need to work with any other plateform they
want in what ever way they want to"*

A rule nobody measures is a rule nobody keeps. `scripts/check_channel_agnostic.py`
counts channel names reaching the runtime in the user substrate and compares
against a committed baseline, so the number can only go down.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_channel_agnostic.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_channel_agnostic", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_channel_agnostic"] = module
    spec.loader.exec_module(module)
    return module


def test_the_substrate_has_not_grown_channel_specific_code():
    """The ratchet itself. Deleting is free; adding is not."""
    assert _module().main([]) == 0


def test_the_baseline_matches_what_is_actually_there():
    """A baseline that drifted from reality would pass while hiding growth."""
    module = _module()
    assert module.survey() == module.load_baseline()


def test_docstrings_do_not_count(tmp_path):
    """Most mentions in this tree are prose explaining why something IS
    agnostic. Counting those would make the rule unmeetable, so nobody would
    keep it."""
    module = _module()
    source = tmp_path / "prose.py"
    source.write_text(
        '"""This module is deliberately agnostic: no GitHub logic lives here."""\n'
        "\n"
        "def f():\n"
        '    """Not GitHub-specific either, despite the word GitHub."""\n'
        "    return 1\n",
        encoding="utf-8",
    )
    assert [t for t in module.runtime_strings(source) if "github" in t.lower()] == []


def test_a_runtime_literal_does_count(tmp_path):
    """The other half: a channel name the code actually uses is a hit."""
    module = _module()
    source = tmp_path / "real.py"
    source.write_text(
        '"""Agnostic, allegedly."""\n'
        "\n"
        "def f():\n"
        '    return "https://api.github.com"\n',
        encoding="utf-8",
    )
    hits = [t for t in module.runtime_strings(source) if "github" in t.lower()]
    assert hits == ["https://api.github.com"]


def test_a_relocated_docstring_is_exempt_but_only_its_own_value(tmp_path):
    """2026-09-26: `write_graph`'s chapters left its docstring for a module
    constant so they stop riding on every model round-trip of every served turn.
    The text did not change, so counting it now would make the rule unmeetable for
    exactly the reason docstrings are exempt -- but the exemption must be the
    NAMED constant's value only, never a licence for the rest of the file."""
    module = _module()
    name = sorted(module.DOCUMENTATION_CONSTANTS)[0]
    source = tmp_path / "relocated.py"
    source.write_text(
        '"""Agnostic, allegedly."""\n'
        "\n"
        f'{name} = """Ask for a GitHub key the way the site names it."""\n'
        '_OTHER_CONSTANT = """A GitHub mention in an unlisted constant."""\n'
        "\n"
        "def f():\n"
        '    return "https://api.github.com"\n',
        encoding="utf-8",
    )
    hits = [t for t in module.runtime_strings(source) if "github" in t.lower()]
    assert "Ask for a GitHub key the way the site names it." not in hits
    assert "A GitHub mention in an unlisted constant." in hits
    assert "https://api.github.com" in hits


def test_every_exempt_documentation_constant_still_exists():
    """A stale name in the exemption list is an exemption nobody can audit."""
    module = _module()
    from tinyassets import engine_mcp_server

    for name in module.DOCUMENTATION_CONSTANTS:
        assert isinstance(getattr(engine_mcp_server, name), str)


def test_the_platform_acting_as_itself_is_listed_not_hidden():
    """Billing its own customers and shipping its own releases are not user
    capabilities. They are exempt BY NAME so the exemption can be argued with,
    rather than by a pattern that quietly swallows new files."""
    module = _module()
    assert "tinyassets/billing/stripe_adapter.py" in module.PLATFORM_OWN
    for rel in module.PLATFORM_OWN:
        assert (REPO_ROOT / rel).is_file(), f"{rel} is exempt but does not exist"


@pytest.mark.parametrize("channel", ["github", "slack", "notion", "stripe"])
def test_the_rule_is_about_any_channel_not_just_github(channel):
    """The founder said GitHub because it was in front of them, and then said
    'nor should any other spasific channel code excist'."""
    assert channel in _module().CHANNELS


@pytest.mark.parametrize(
    "vendor", ["openai", "chatgpt", "anthropic", "claude", "ollama", "openrouter"]
)
def test_the_same_rule_covers_compute(vendor):
    """Founder, same day: "the llm's the universe has access to ... all
    agnostic shapes. we shouldnt have a chatgpt spacific path."

    `connect_compute` already promises exactly that in its own contract -- ANY
    compute provider, no per-provider code, no allowlist -- so the count is the
    distance between the promise and the tree."""
    assert vendor in _module().VENDORS
