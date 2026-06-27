"""Tests for tinyassets.context.guardrails module."""


from tinyassets.context.guardrails import (
    FilterGuardrail,
    GuardrailPipeline,
    PaginationGuardrail,
    SummarizationGuardrail,
    build_retrieval_pipeline,
)


class TestFilterGuardrail:
    """Tests for FilterGuardrail."""

    def test_filter_by_relevance_exact_match(self):
        """Test filtering with exact keyword matches."""
        results = [
            {"text": "The quick brown fox"},
            {"text": "A slow turtle"},
            {"text": "The quick fox jumps high"},
        ]

        filtered = FilterGuardrail.filter_by_relevance(
            results, query="quick fox", max_results=10
        )

        # Results with "quick" and "fox" should rank higher
        assert filtered[0]["text"] == "The quick fox jumps high"

    def test_filter_by_relevance_max_results(self):
        """Test that max_results is respected."""
        results = [
            {"text": "Test query term"},
            {"text": "Test query term"},
            {"text": "Test query term"},
            {"text": "Test query term"},
            {"text": "Test query term"},
        ]

        filtered = FilterGuardrail.filter_by_relevance(
            results, query="test", max_results=2
        )

        assert len(filtered) == 2

    def test_filter_by_relevance_empty_query(self):
        """Test that empty query returns original results."""
        results = [{"text": "A"}, {"text": "B"}]

        filtered = FilterGuardrail.filter_by_relevance(results, query="", max_results=10)

        assert len(filtered) == 2

    def test_filter_by_relevance_empty_results(self):
        """Test that empty results list is handled."""
        filtered = FilterGuardrail.filter_by_relevance(
            [], query="test", max_results=10
        )

        assert filtered == []

    def test_filter_by_relevance_content_field(self):
        """Test filtering with 'content' field."""
        results = [
            {"content": "The quick fox"},
            {"content": "A slow turtle"},
        ]

        filtered = FilterGuardrail.filter_by_relevance(
            results, query="quick", max_results=10
        )

        assert len(filtered) > 0
        assert "quick" in filtered[0]["content"]

    def test_filter_by_scope_matching(self):
        """Test scope filtering with matching scope."""
        results = [
            {"text": "A", "scope": {"universe_id": "u1", "branch_id": "b1"}},
            {"text": "B", "scope": {"universe_id": "u2", "branch_id": "b1"}},
            {"text": "C", "scope": {"universe_id": "u1", "branch_id": "b2"}},
        ]

        filtered = FilterGuardrail.filter_by_scope(
            results, scope={"universe_id": "u1"}
        )

        assert len(filtered) == 2
        for result in filtered:
            assert result["scope"]["universe_id"] == "u1"

    def test_filter_by_scope_no_scope_info(self):
        """Test that results without scope info are included."""
        results = [
            {"text": "A", "scope": {"universe_id": "u1"}},
            {"text": "B"},  # No scope
        ]

        filtered = FilterGuardrail.filter_by_scope(
            results, scope={"universe_id": "u1"}
        )

        assert len(filtered) == 2

    def test_filter_by_scope_empty_scope(self):
        """Test that empty scope parameter returns all results."""
        results = [
            {"text": "A", "scope": {"universe_id": "u1"}},
            {"text": "B", "scope": {"universe_id": "u2"}},
        ]

        filtered = FilterGuardrail.filter_by_scope(results, scope={})

        assert len(filtered) == 2

    def test_filter_by_recency_all_recent(self):
        """Test filtering all recent results."""
        import time

        now = time.time()
        results = [
            {"text": "A", "timestamp": now - 3600},  # 1 hour old
            {"text": "B", "timestamp": now - 1800},  # 30 min old
        ]

        # Max age: 2 hours
        filtered = FilterGuardrail.filter_by_recency(results, max_age_hours=2)

        assert len(filtered) == 2

    def test_filter_by_recency_removes_old(self):
        """Test that old results are removed."""
        import time

        now = time.time()
        results = [
            {"text": "A", "timestamp": now - (48 * 3600)},  # 2 days old
            {"text": "B", "timestamp": now - 3600},  # 1 hour old
        ]

        # Max age: 24 hours
        filtered = FilterGuardrail.filter_by_recency(results, max_age_hours=24)

        assert len(filtered) == 1
        assert filtered[0]["text"] == "B"

    def test_filter_by_recency_no_max_age(self):
        """Test that None max_age returns all results."""
        results = [
            {"text": "A", "timestamp": 1000},
            {"text": "B", "timestamp": 2000},
        ]

        filtered = FilterGuardrail.filter_by_recency(results, max_age_hours=None)

        assert len(filtered) == 2

    def test_filter_by_recency_iso_timestamp(self):
        """Test filtering with ISO timestamp."""
        results = [
            {"text": "A", "timestamp": "2026-04-01T10:00:00Z"},
            {"text": "B", "timestamp": "2026-04-06T10:00:00Z"},
        ]

        # Filter for last 5 days (should include only the recent one)
        filtered = FilterGuardrail.filter_by_recency(results, max_age_hours=24)

        # One should be filtered as too old
        assert len(filtered) <= 2


class TestPaginationGuardrail:
    """Tests for PaginationGuardrail."""

    def test_paginate_first_page(self):
        """Test getting first page."""
        results = list(range(50))

        paginated = PaginationGuardrail.paginate(
            results, page_size=10, page=0
        )

        assert len(paginated.items) == 10
        assert paginated.items[0] == 0
        assert paginated.items[-1] == 9
        assert paginated.page == 0
        assert paginated.total == 50
        assert paginated.has_more is True

    def test_paginate_middle_page(self):
        """Test getting a middle page."""
        results = list(range(50))

        paginated = PaginationGuardrail.paginate(
            results, page_size=10, page=2
        )

        assert len(paginated.items) == 10
        assert paginated.items[0] == 20
        assert paginated.items[-1] == 29
        assert paginated.page == 2
        assert paginated.has_more is True

    def test_paginate_last_page(self):
        """Test getting last page."""
        results = list(range(50))

        paginated = PaginationGuardrail.paginate(
            results, page_size=10, page=4
        )

        assert len(paginated.items) == 10
        assert paginated.items[0] == 40
        assert paginated.has_more is False

    def test_paginate_partial_last_page(self):
        """Test partial last page."""
        results = list(range(45))

        paginated = PaginationGuardrail.paginate(
            results, page_size=10, page=4
        )

        assert len(paginated.items) == 5
        assert paginated.has_more is False

    def test_paginate_negative_page(self):
        """Test that negative page defaults to 0."""
        results = list(range(50))

        paginated = PaginationGuardrail.paginate(
            results, page_size=10, page=-1
        )

        assert paginated.page == 0
        assert paginated.items[0] == 0

    def test_paginate_invalid_page_size(self):
        """Test that invalid page size defaults."""
        results = list(range(50))

        paginated = PaginationGuardrail.paginate(
            results, page_size=0, page=0
        )

        # Should use default page_size of 20
        assert len(paginated.items) == 20


class TestSummarizationGuardrail:
    """Tests for SummarizationGuardrail."""

    def test_summarize_if_large_short_content(self):
        """Test that short content is unchanged."""
        content = "This is a short piece of text."

        summarized = SummarizationGuardrail.summarize_if_large(
            content, max_tokens=1000
        )

        assert summarized == content
        assert "[truncated]" not in summarized

    def test_summarize_if_large_long_content(self):
        """Test that long content is truncated."""
        content = "A" * 10000

        summarized = SummarizationGuardrail.summarize_if_large(
            content, max_tokens=100
        )

        assert len(summarized) < len(content)
        assert "[truncated]" in summarized

    def test_summarize_if_large_breaks_at_period(self):
        """Test that truncation breaks at sentence boundary."""
        content = (
            "This is sentence one. This is sentence two. " + "A" * 5000
        )

        summarized = SummarizationGuardrail.summarize_if_large(
            content, max_tokens=50
        )

        # Should end with period + marker
        assert summarized.rstrip().endswith("[truncated]")
        # Should have found the period
        assert "." in summarized

    def test_summarize_if_large_empty_content(self):
        """Test that empty content is handled."""
        summarized = SummarizationGuardrail.summarize_if_large("", max_tokens=100)

        assert summarized == ""

    def test_summarize_list_single_item(self):
        """Test summarizing single item."""
        items = ["This is a test item"]

        summarized = SummarizationGuardrail.summarize_list(
            items, max_total_tokens=1000
        )

        assert len(summarized) == 1
        assert summarized[0] == items[0]

    def test_summarize_list_multiple_items(self):
        """Test summarizing multiple items."""
        items = [
            "A" * 1000,
            "B" * 1000,
            "C" * 1000,
        ]

        summarized = SummarizationGuardrail.summarize_list(
            items, max_total_tokens=1000
        )

        assert len(summarized) == 3
        # Total should be less than original
        total_len = sum(len(s) for s in summarized)
        original_len = sum(len(i) for i in items)
        assert total_len < original_len

    def test_summarize_list_empty(self):
        """Test summarizing empty list."""
        summarized = SummarizationGuardrail.summarize_list([], max_total_tokens=1000)

        assert summarized == []


class TestGuardrailPipeline:
    """Tests for GuardrailPipeline."""

    def test_pipeline_empty(self):
        """Test empty pipeline returns input unchanged."""
        pipeline = GuardrailPipeline()
        data = [{"text": "test"}]

        result = pipeline.apply(data)

        assert result == data

    def test_pipeline_single_step(self):
        """Test pipeline with single step."""
        pipeline = GuardrailPipeline()
        pipeline.add_step(lambda x: x[:2])

        data = [1, 2, 3, 4, 5]
        result = pipeline.apply(data)

        assert result == [1, 2]

    def test_pipeline_multiple_steps(self):
        """Test pipeline with multiple steps."""
        pipeline = GuardrailPipeline()
        pipeline.add_step(lambda x: x[:4])  # Take first 4
        pipeline.add_step(lambda x: [i * 2 for i in x])  # Double each

        data = [1, 2, 3, 4, 5, 6]
        result = pipeline.apply(data)

        assert result == [2, 4, 6, 8]

    def test_pipeline_chaining(self):
        """Test that add_step returns self for chaining."""
        pipeline = (
            GuardrailPipeline()
            .add_step(lambda x: x[:3])
            .add_step(lambda x: [i * 2 for i in x])
        )

        data = [1, 2, 3, 4, 5]
        result = pipeline.apply(data)

        assert result == [2, 4, 6]

    def test_pipeline_handles_error(self):
        """Test that pipeline continues after error."""
        def failing_step(x):
            raise ValueError("Test error")

        def identity_step(x):
            return x

        pipeline = GuardrailPipeline()
        pipeline.add_step(failing_step)
        pipeline.add_step(identity_step)

        data = [1, 2, 3]
        result = pipeline.apply(data)

        # Should return input from identity step after failing step
        assert result == data


class TestBuildRetrievalPipeline:
    """Tests for build_retrieval_pipeline helper."""

    def test_build_with_all_options(self):
        """Test building pipeline with all options."""
        pipeline = build_retrieval_pipeline(
            query="test",
            scope={"universe_id": "u1"},
            max_age_hours=24,
            max_results=10,
            page_size=5,
        )

        assert len(pipeline._steps) > 0

    def test_build_with_query_only(self):
        """Test building pipeline with only query."""
        pipeline = build_retrieval_pipeline(query="test")

        assert len(pipeline._steps) == 1

    def test_build_with_no_options(self):
        """Test building empty pipeline."""
        pipeline = build_retrieval_pipeline()

        assert len(pipeline._steps) == 0

    def test_build_pipeline_applies_correctly(self):
        """Test that built pipeline works correctly."""
        results = [
            {"text": "quick fox", "scope": {"universe_id": "u1"}},
            {"text": "slow turtle", "scope": {"universe_id": "u1"}},
            {"text": "quick wolf", "scope": {"universe_id": "u2"}},
        ]

        pipeline = build_retrieval_pipeline(
            query="quick",
            scope={"universe_id": "u1"},
            max_results=5,
        )

        result = pipeline.apply(results)

        # Should have filtered by scope
        assert all(r["scope"]["universe_id"] == "u1" for r in result)
        # Should have kept "quick" results
        assert all("quick" in r["text"] for r in result)
