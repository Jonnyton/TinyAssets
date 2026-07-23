# 2026-07-22 — activity-lane-files

Replaced the single append-only activity log with one file per lane. Union merge was tried first and rejected: GitHub reported a union-ruled append collision as CONFLICTING (disposable PR #1525), and a bare merge does not load .gitattributes without --attr-source.
