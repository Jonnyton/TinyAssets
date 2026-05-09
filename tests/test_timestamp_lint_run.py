from datetime import datetime, timedelta, timezone

from scripts.timestamp_lint_run import lint_markdown, main

WRITE_TIME = datetime(2026, 5, 8, 1, 25, 0, tzinfo=timezone.utc)


def _lint(tmp_path, text):
    page = tmp_path / "page.md"
    page.write_text(text, encoding="utf-8")
    return lint_markdown(
        page,
        write_time_utc=WRITE_TIME,
        tolerance=timedelta(seconds=60),
    )


def test_rejects_typed_timestamp_future_of_write_time(tmp_path):
    violations = _lint(
        tmp_path,
        """---
title: Example
authored_at_utc: 2026-05-08T08:15:00Z
---

Body.
""",
    )

    assert len(violations) == 1
    assert violations[0].field == "authored_at_utc"
    assert violations[0].reason == "typed timestamp field is in the future of write_time_utc"


def test_rejects_typed_timestamp_without_z_suffix(tmp_path):
    violations = _lint(
        tmp_path,
        """---
title: Example
updated_at_utc: 2026-05-08T01:24:00+00:00
---
""",
    )

    assert len(violations) == 1
    assert violations[0].reason == "typed timestamp field must use UTC ISO8601 Z suffix"


def test_ignores_prose_and_untyped_source_dates(tmp_path):
    violations = _lint(
        tmp_path,
        """---
title: External Source
source_timezone: America/New_York
---

Published 2024-03-15.
The source says the meeting happened at 7pm local time.
""",
    )

    assert violations == []


def test_lints_yaml_state_blocks(tmp_path):
    violations = _lint(
        tmp_path,
        """# State block

```yaml
position:
  stance: accept
  reason:
    type: substantive
refactor_pass_at_utc: 2026-05-08T08:45:00Z
```
""",
    )

    assert len(violations) == 1
    assert violations[0].field == "refactor_pass_at_utc"


def test_allows_explicit_unknown_sidecar_timestamp(tmp_path):
    violations = _lint(
        tmp_path,
        """---
title: Source Sidecar
source_metadata:
  source_observed_at_utc: unknown
  source_published_at_utc: null
  ingested_at: 2026-05-08T01:24:00Z
---
""",
    )

    assert violations == []


def test_cli_returns_nonzero_for_violations(tmp_path, capsys):
    page = tmp_path / "page.md"
    page.write_text(
        """---
authored_at_utc: 2026-05-08T08:15:00Z
---
""",
        encoding="utf-8",
    )

    code = main(
        [
            str(page),
            "--write-time",
            "2026-05-08T01:25:00Z",
            "--tolerance-seconds",
            "60",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "future of write_time_utc" in captured.err
