"""The connect surface offers any LLM, not two vendors.

Founder, 2026-09-03: *"the llm's the universe has access to ... all agnostic
shapes. we shouldnt have a chatgpt spacific path. the request popup that comes
up if your universe isnt powered should allow the user to connect any llm
source they want to thier universe."*

The capability was already underneath -- `bind_serving_provider` resolves any
registered compute connection and `_open_serving_context` authorizes it by
ownership. What a user was SHOWN was a two-item dropdown, and a capability the
surface never offers is not one a user has.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

from tinyassets.onboarding import render_app_html


@pytest.fixture(scope="module")
def app_html() -> str:
    html, _csp = render_app_html()
    return html


def test_the_service_picker_offers_more_than_two_vendors(app_html):
    picker = re.search(
        r'<select id="connect-service".*?</select>', app_html, re.S,
    )
    assert picker is not None, "the service picker is gone"
    options = re.findall(r'<option value="([^"]+)"', picker.group(0))
    assert "__endpoint__" in options, (
        f"no path to connect an arbitrary endpoint; options were {options}"
    )


def test_the_endpoint_form_asks_for_what_connect_compute_needs(app_html):
    """A URL, a wire protocol and a model -- the arguments the substrate takes.
    Not a vendor name, because the platform does not keep a list of vendors."""
    for field in (
        'id="endpoint-name"',
        'id="endpoint-url"',
        'id="endpoint-protocol"',
        'id="endpoint-model"',
        'id="endpoint-key"',
    ):
        assert field in app_html, field


def test_the_endpoint_path_uses_the_agnostic_calls(app_html):
    """connect_http deposits the key, connect_compute registers the descriptor
    on that grant, and the universe is pointed at the returned id. All three
    already existed; none of them names a vendor."""
    assert "MCP.connectHTTP(name,key" in app_html
    assert "MCP.connectCompute({" in app_html
    assert "access_method:\"api_key_http\"" in app_html
    assert "ref:deposit.grant_id" in app_html


def test_the_service_label_is_not_a_two_way_ternary(app_html):
    """`service==="codex" ? "OpenAI" : "Claude"` could only ever name two
    things, so any third connection would have rendered as "Claude"."""
    assert 'service==="codex" ? "OpenAI" : "Claude"' not in app_html
    assert "SERVICE_LABELS[service] || service" in app_html


def test_an_endpoint_key_never_rides_over_plain_http(app_html):
    """The key is the user's. It goes to their endpoint over TLS or not at
    all -- a refusal, not a warning."""
    assert 'parsed.protocol!=="https:"' in app_html


def test_the_key_leaves_the_dom_before_any_await(app_html):
    """Same rule the subscription path already follows: the secret is cleared
    from the field BEFORE the first await, on every path out."""
    body = app_html[app_html.index("async function depositEndpoint") :]
    body = body[: body.index("$(\"btn-deposit\").addEventListener")]
    cleared = body.index('keyEl.value="";')
    first_await = body.index("await ")
    assert cleared < first_await, "the key outlives the first await"


def test_the_endpoint_pane_names_no_vendor():
    """A form for "any LLM" whose examples are four particular companies is
    still a vendor list, just an implicit one. The existing HTTP form set the
    convention -- `api.example.com`, "OAuth 1.0a - 4 keys" -- and the repo
    already caught me breaking it here once.

    The forbidden names come from `check_channel_agnostic.py` rather than a
    second list of my own: one fact, one definition.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "check_channel_agnostic.py"
    spec = importlib.util.spec_from_file_location("check_channel_agnostic", script)
    ratchet = importlib.util.module_from_spec(spec)
    sys.modules["check_channel_agnostic"] = ratchet
    spec.loader.exec_module(ratchet)

    html, _csp = render_app_html()
    pane = html[html.index('id="connect-endpoint"') :]
    pane = pane[: pane.index("btn-deposit")]

    # `value="..."` is the machine contract -- the ENCODERS protocol ids -- and
    # is pinned positively below, exactly as the existing form requires
    # `value="oauth1a"` while forbidding the label "X/Twitter". Everything a
    # user actually READS is what must name nobody: labels, help text and
    # placeholders.
    visible = re.sub(r'value="[^"]*"', "", pane).lower()
    named = sorted({v for v in ratchet.VENDORS if v in visible})
    assert not named, f"the any-LLM form shows vendor names: {named}"

    # ...and the protocol ids really are still there, so a form that dropped
    # them could not pass this by having nothing left to check.
    assert 'value="openai_chat"' in pane
    assert 'value="anthropic_messages"' in pane


def _vendor_names():
    """The forbidden names, from `check_channel_agnostic.py`: one fact, one definition."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "check_channel_agnostic.py"
    spec = importlib.util.spec_from_file_location("check_channel_agnostic", script)
    ratchet = importlib.util.module_from_spec(spec)
    sys.modules["check_channel_agnostic"] = ratchet
    spec.loader.exec_module(ratchet)
    return ratchet.VENDORS


def test_the_whole_connect_surface_names_no_vendor(app_html):
    """Not just the endpoint pane -- the picker above it too.

    The pane-scoped test started at `connect-endpoint`, so it could not see the
    two `<option>` labels, which read two company names until the founder ruled
    on it (2026-09-03: reword neutrally). The options are now named by the
    CREDENTIAL SHAPE the user hands over.
    """
    card = app_html[app_html.index('id="connect-service"'):]
    card = card[: card.index("btn-deposit")]
    visible = re.sub(r'value="[^"]*"', "", card).lower()
    named = sorted({v for v in _vendor_names() if v in visible})
    assert not named, f"the connect surface shows vendor names: {named}"

    # The wire ids must survive the rewording -- a picker that renamed the
    # VALUES would break every existing binding while passing the check above.
    assert 'value="claude"' in card
    assert 'value="codex"' in card
    assert 'value="__endpoint__"' in card


def test_the_serving_status_lines_name_no_vendor(app_html):
    """`servingSentence` is rendered back to the user after a deposit, so the
    label table is user-visible copy and falls under the same rule."""
    labels = re.search(r"const SERVICE_LABELS=\{.*?\};", app_html, re.S)
    assert labels is not None, "the label table is gone"
    # The KEYS are the wire ids -- the same machine contract `value="..."` is,
    # and exempt for the same reason. Only the values are read by a user.
    values = re.findall(r':"([^"]+)"', labels.group(0))
    assert values, "the label table has no labels"
    named = sorted({v for v in _vendor_names() if v in " ".join(values).lower()})
    assert not named, f"the serving status lines name vendors: {named}"

    # Each label has to read as a noun phrase in BOTH positions it appears in:
    # "...runs its background work on X." and "X connected."
    for value in values:
        assert not value.endswith("."), f"{value!r} is a sentence, not a label"
        assert value[0].islower(), f"{value!r} cannot sit mid-sentence"
