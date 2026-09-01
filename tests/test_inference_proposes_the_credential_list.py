"""Inference says WHICH credentials a service needs, not just where to call it.

The proposal already identified the service and one exact endpoint. It did not
say what the owner must actually paste, so the ask fell back to a single box
labelled "paste the key" — and for an OAuth 1.0a service that is four or five
values the owner has to work out and match up themselves.

The list is validated by the REQUEST validator, not by a second set of rules
here. If inference proposes it, the ask accepts it — a link rule cannot come to
mean two things in two places, which is exactly how a consent key ended up with
two spellings twice in one day.

There is no table of services in the platform and these tests assume none.
"""
from __future__ import annotations

from tinyassets.api.connection_inference import _validated_credentials


def test_a_multi_value_service_survives_intact() -> None:
    """The OAuth 1.0a case, which is what motivated this."""
    proposed = _validated_credentials(
        [
            {
                "name": "api_key",
                "label": "API Key",
                "help": "Developer Portal -> your app -> Keys and tokens",
                "url": "https://developer.example.com/portal",
            },
            {"name": "api_secret", "label": "API Key Secret"},
            {"name": "access_token", "label": "Access Token"},
            {"name": "access_token_secret", "label": "Access Token Secret"},
        ],
        "oauth1a",
    )
    assert [c["name"] for c in proposed] == [
        "api_key",
        "api_secret",
        "access_token",
        "access_token_secret",
    ]
    assert proposed[0]["label"] == "API Key"
    assert proposed[0]["url"] == "https://developer.example.com/portal"
    assert all(c["type"] == "secret" for c in proposed)


def test_a_service_nobody_enumerated_is_treated_the_same() -> None:
    proposed = _validated_credentials(
        [
            {
                "name": "token",
                "label": "Personal Access Token",
                "help": "Profile -> Settings -> Access tokens -> New token",
                "url": "https://git.internal.example/-/profile/personal_access_tokens",
            }
        ]
    )
    assert proposed[0]["label"] == "Personal Access Token"
    assert proposed[0]["url"].startswith("https://git.internal.example")


def test_nothing_proposed_is_not_an_error() -> None:
    """A model that is unsure should say nothing; the ordinary single-secret ask
    still works, and a wrong click path is worse than none."""
    assert _validated_credentials(None) == []
    assert _validated_credentials([]) == []
    assert _validated_credentials("not a list") == []


def test_a_dangerous_link_drops_the_whole_list() -> None:
    """One poisoned entry must not ship alongside three good ones.

    A partial list is worse than none: the owner pastes what they were shown and
    is told afterwards that something else was missing. And the entry is
    poisoned in the one way that matters — a link the owner is invited to click
    while being asked for a secret.
    """
    proposed = _validated_credentials(
        [
            {"name": "username", "label": "User"},
            {"name": "password", "label": "Secret", "url": "javascript:alert(1)"},
        ],
        "basic",
    )
    assert proposed == []


def test_a_link_with_credentials_in_it_drops_the_list() -> None:
    proposed = _validated_credentials(
        [{"name": "k", "label": "Key", "url": "https://user:pw@evil.example/x"}]
    )
    assert proposed == []


def test_duplicate_names_drop_the_list() -> None:
    """Duplicates collide as DOM ids and can leave a secret in the page; the
    request validator refuses them and this inherits that refusal rather than
    re-deciding it."""
    proposed = _validated_credentials(
        [{"name": "k", "label": "One"}, {"name": "k", "label": "Two"}], "basic"
    )
    assert proposed == []


def test_entries_without_a_name_are_skipped_not_fatal() -> None:
    proposed = _validated_credentials(
        [{"label": "no name"}, {"name": "api_key", "label": "API Key"}], "bearer"
    )
    assert [c["name"] for c in proposed] == ["api_key"]


def test_the_prompt_asks_for_the_sites_own_words() -> None:
    """The label has to be what the owner is reading on that page, or it is one
    more thing for them to work out."""
    import tinyassets.api.connection_inference as mod

    assert "credentials" in mod._SYSTEM
    assert "SITE'S OWN name" in mod._SYSTEM
    assert "no list of known services" in mod._SYSTEM
