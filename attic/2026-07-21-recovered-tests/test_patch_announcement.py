import json

from scripts.social.patch_announcement import (
    CommitCredit,
    Contributor,
    actor_ids_from_commit_message,
    coauthors_from_message,
    compose_post_text,
    credited_contributors,
    is_patch_announcement_eligible,
    load_contributors,
    missing_github_credit,
    resolve_actors,
    shorten,
)


def write_contributors(tmp_path):
    path = tmp_path / "CONTRIBUTORS.md"
    path.write_text(
        "\n".join(
            [
                "# Contributors",
                "",
                "| Actor ID | GitHub Handle | Display Name | X Handle | Social Opt-In |",
                "|---|---|---|---|---|",
                "| alice | alicegh | Alice A | alicex | yes |",
                "| bob | bobgh | Bob B | | no |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_load_contributors_parses_github_and_social_fields(tmp_path):
    contributors = load_contributors(write_contributors(tmp_path))

    assert contributors["alice"].trailer == (
        "Co-Authored-By: Alice A <alicegh@users.noreply.github.com>"
    )
    assert contributors["alice"].x_mention == "@alicex"
    assert contributors["bob"].x_mention == ""


def test_resolve_actors_dedupes_and_reports_missing(tmp_path):
    contributors = load_contributors(write_contributors(tmp_path))

    resolved, missing = resolve_actors(["alice", "alice", "unknown"], contributors)

    assert [contributor.actor_id for contributor in resolved] == ["alice"]
    assert missing == ["unknown"]


def test_coauthors_from_message_extracts_landed_github_credit():
    credits = coauthors_from_message(
        "Subject\n\n"
        "Co-Authored-By: Alice A <alicegh@users.noreply.github.com>\n"
        "co-authored-by: Bob B <bobgh@users.noreply.github.com>\n"
    )

    assert [credit.github_handle for credit in credits] == ["alicegh", "bobgh"]


def test_missing_github_credit_uses_contributor_email():
    contributors = [
        Contributor(actor_id="alice", github_handle="alicegh", display_name="Alice A"),
        Contributor(actor_id="bob", github_handle="bobgh", display_name="Bob B"),
    ]
    credits = [CommitCredit("Alice A", "alicegh@users.noreply.github.com", "alicegh")]

    assert missing_github_credit(contributors, credits) == [contributors[1]]


def test_credited_contributors_filters_to_landed_github_credit():
    contributors = [
        Contributor(actor_id="alice", github_handle="alicegh", display_name="Alice A"),
        Contributor(actor_id="bob", github_handle="bobgh", display_name="Bob B"),
    ]
    credits = [CommitCredit("Alice A", "alicegh@users.noreply.github.com", "alicegh")]

    assert credited_contributors(contributors, credits) == [contributors[0]]


def test_compose_post_text_uses_opt_in_x_mentions():
    text = compose_post_text(
        title="Fix stuck writer gate",
        commit="abcdef123456",
        repo_url="https://github.com/Jonnyton/Workflow",
        credits=[CommitCredit("Alice A", "alicegh@users.noreply.github.com", "alicegh")],
        contributors=[
            Contributor(
                actor_id="alice",
                github_handle="alicegh",
                display_name="Alice A",
                x_handle="alicex",
                social_opt_in=True,
            )
        ],
    )

    assert "Patch landed: Fix stuck writer gate" in text
    assert "Contributors: @alicex" in text
    assert "Verified on main: abcdef1" in text


def test_compose_post_text_falls_back_to_github_credit_without_social_opt_in():
    text = compose_post_text(
        title="Fix stuck writer gate",
        commit="abcdef123456",
        repo_url="https://github.com/Jonnyton/Workflow",
        credits=[CommitCredit("Bob B", "bobgh@users.noreply.github.com", "bobgh")],
        contributors=[
            Contributor(
                actor_id="bob",
                github_handle="bobgh",
                display_name="Bob B",
                x_handle="bobx",
                social_opt_in=False,
            )
        ],
    )

    assert "GitHub credit: bobgh" in text
    assert "@bobx" not in text


def test_patch_marker_required_for_automatic_announcements():
    assert is_patch_announcement_eligible(
        commit_message="Fix thing\n\nPatch-Id: patch-123",
        actor_ids=[],
    )
    assert is_patch_announcement_eligible(
        commit_message="Fix thing",
        actor_ids=["alice"],
    )
    assert not is_patch_announcement_eligible(
        commit_message="Routine docs edit",
        actor_ids=[],
    )


def test_patch_contributors_marker_supplies_actor_ids():
    assert actor_ids_from_commit_message("Patch-Contributors: alice, bob") == ["alice", "bob"]


def test_shorten_uses_ascii_ellipsis():
    assert shorten("abcdef", 5) == "ab..."


def test_payload_shape_remains_serializable_for_workflow(tmp_path):
    contributors = load_contributors(write_contributors(tmp_path))
    resolved, missing = resolve_actors(["alice"], contributors)

    payload = {
        "resolved_contributors": [contributor.__dict__ for contributor in resolved],
        "missing_actor_ids": missing,
    }

    assert json.loads(json.dumps(payload))["missing_actor_ids"] == []
