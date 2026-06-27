"""Tests for the robust JSON parsing utility."""

from __future__ import annotations

from tinyassets.utils.json_parsing import parse_llm_json


class TestParseLlmJson:
    def test_valid_json(self):
        assert parse_llm_json('{"a": 1}') == {"a": 1}

    def test_valid_json_list(self):
        assert parse_llm_json('[1, 2, 3]') == [1, 2, 3]

    def test_markdown_fenced_json(self):
        raw = '```json\n{"key": "value"}\n```'
        assert parse_llm_json(raw) == {"key": "value"}

    def test_markdown_fenced_no_lang(self):
        raw = '```\n{"key": "value"}\n```'
        assert parse_llm_json(raw) == {"key": "value"}

    def test_trailing_comma(self):
        raw = '{"a": 1, "b": 2,}'
        result = parse_llm_json(raw)
        assert result == {"a": 1, "b": 2}

    def test_missing_closing_brace(self):
        raw = '{"a": 1, "b": 2'
        result = parse_llm_json(raw)
        assert isinstance(result, dict)
        assert result["a"] == 1

    def test_embedded_in_prose(self):
        raw = 'Here is the plan:\n{"beats": [1, 2]}\nEnd of plan.'
        result = parse_llm_json(raw, expect_type=dict)
        assert result == {"beats": [1, 2]}

    def test_empty_string_returns_fallback(self):
        assert parse_llm_json("") is None
        assert parse_llm_json("", fallback=[]) == []

    def test_whitespace_only_returns_fallback(self):
        assert parse_llm_json("   \n  ", fallback="default") == "default"

    def test_expect_type_dict(self):
        assert parse_llm_json('{"a": 1}', expect_type=dict) == {"a": 1}

    def test_expect_type_list(self):
        assert parse_llm_json("[1, 2]", expect_type=list) == [1, 2]

    def test_expect_type_mismatch_returns_fallback(self):
        result = parse_llm_json('{"a": 1}', expect_type=list, fallback=[])
        assert result == []

    def test_single_quotes_repaired(self):
        raw = "{'key': 'value'}"
        result = parse_llm_json(raw, expect_type=dict)
        assert result is not None
        assert result.get("key") == "value"

    def test_none_input_returns_fallback(self):
        # Handles None-ish input gracefully
        assert parse_llm_json(None, fallback={}) == {}

    def test_pure_prose_returns_fallback(self):
        raw = "This is just prose with no JSON at all."
        result = parse_llm_json(raw, expect_type=dict, fallback={})
        assert result == {}

    def test_nested_structure(self):
        raw = '```json\n{"alternatives": [{"beats": [{"n": 1}]}]}\n```'
        result = parse_llm_json(raw, expect_type=dict)
        assert result is not None
        assert len(result["alternatives"]) == 1

    def test_json_with_comments(self):
        raw = '{\n  // this is a comment\n  "a": 1\n}'
        result = parse_llm_json(raw, expect_type=dict)
        # json_repair should handle or strip comments
        assert result is not None

    def test_truncated_list(self):
        raw = '[{"id": 1}, {"id": 2}'
        result = parse_llm_json(raw, expect_type=list)
        assert result is not None
        assert isinstance(result, list)
