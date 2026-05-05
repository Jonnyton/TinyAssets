from workflow.api.wiki import _slugify_title


def test_slugify_title_truncation_prefers_word_boundary():
    title = "Wiki slug generation truncates mid-word instead of at word boundaries"

    assert (
        _slugify_title(title, max_len=60)
        == "wiki-slug-generation-truncates-mid-word-instead-of-at-word"
    )


def test_slugify_title_truncates_single_long_word_at_max_len():
    assert _slugify_title("a" * 100, max_len=60) == "a" * 60
