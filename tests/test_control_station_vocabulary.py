"""Grep-tests for the vocabulary discipline section of the control_station prompt.

Spec: feedback_user_vocabulary_discipline — chatbot must not introduce engine
terms ("branch", "node", "canon", "graph", "DAG", "few-shot reference") before
the user does. The prompt's Vocabulary discipline section encodes this rule.

Maya LIVE-F3 evidence: "branch" and "canon" leaked into chatbot responses during
live testing even though the user only said "workflow" and "knowledge".
"""

from __future__ import annotations

from tinyassets.api.prompts import _CONTROL_STATION_PROMPT


class TestVocabularyDisciplineSection:
    """Prompt must contain the vocabulary discipline section."""

    def test_section_header_present(self):
        assert "Vocabulary discipline" in _CONTROL_STATION_PROMPT

    def test_banned_term_branch(self):
        assert '"branch" → say "workflow"' in _CONTROL_STATION_PROMPT

    def test_banned_term_node(self):
        assert '"node" → say "step"' in _CONTROL_STATION_PROMPT

    def test_banned_term_canon(self):
        assert '"canon" → say "knowledge"' in _CONTROL_STATION_PROMPT

    def test_banned_term_graph_dag(self):
        assert '"graph" / "DAG"' in _CONTROL_STATION_PROMPT

    def test_banned_term_few_shot(self):
        assert '"few-shot reference"' in _CONTROL_STATION_PROMPT

    def test_mirror_rule_present(self):
        assert 'if the user says "branch", you can say "branch" back' in _CONTROL_STATION_PROMPT

    def test_never_introduce_first_rule(self):
        assert "Never use an engine term first" in _CONTROL_STATION_PROMPT
