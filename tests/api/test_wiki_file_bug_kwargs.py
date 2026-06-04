import json

from workflow.api.helpers import _scoped_wiki_root
from workflow.api.wiki import _ensure_wiki_scaffold, _wiki_file_bug


def _make_wiki_root(tmp_path):
    wiki_root = tmp_path / "wiki"
    _ensure_wiki_scaffold(wiki_root)
    return wiki_root


def test_file_bug_title_only_shell_still_files(tmp_path):
    wiki_root = _make_wiki_root(tmp_path)

    with _scoped_wiki_root(wiki_root):
        response = json.loads(
            _wiki_file_bug(
                component="wiki.shell",
                severity="minor",
                title="Title only filing",
            )
        )

    assert response["status"] == "filed"
    assert response["bug_id"].startswith("BUG-")
    bug_path = wiki_root / response["path"]
    assert bug_path.exists()
    bug_text = bug_path.read_text(encoding="utf-8")
    assert "## What happened\n\n_not specified_" in bug_text
    assert "## What was expected\n\n_not specified_" in bug_text
    assert "warning" not in response


def test_file_bug_falsey_unsupported_body_kwargs_do_not_block_title_only_shell(tmp_path):
    wiki_root = _make_wiki_root(tmp_path)

    with _scoped_wiki_root(wiki_root):
        response = json.loads(
            _wiki_file_bug(
                component="wiki.shell",
                severity="minor",
                title="Falsey unsupported kwargs stay ignored",
                body="",
                content=None,
                body_style=False,
            )
        )

    assert response["status"] == "filed"
    assert (wiki_root / response["path"]).exists()
    assert "warning" not in response


def test_file_bug_rejects_truthy_unsupported_body_kwargs(tmp_path):
    wiki_root = _make_wiki_root(tmp_path)

    with _scoped_wiki_root(wiki_root):
        response = json.loads(
            _wiki_file_bug(
                component="wiki.shell",
                severity="minor",
                title="Truthy unsupported kwargs fail fast",
                body="unexpected markdown body",
                body_style="markdown",
                content_type="text/markdown",
            )
        )

    assert response["error"] == (
        "Unsupported file_bug field(s): body, body_style, content_type. "
        "file_bug only supports the title-only shell plus structured body fields "
        "(repro, observed, expected, workaround); body/content-style kwargs must "
        "be omitted here."
    )
    assert response["hint"] == (
        "Keep title/component/severity and either omit those kwargs or map their "
        "content into repro/observed/expected/workaround."
    )
    assert list((wiki_root / "pages" / "bugs").glob("*.md")) == []
