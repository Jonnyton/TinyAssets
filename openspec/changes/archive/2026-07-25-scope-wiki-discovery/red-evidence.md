# RED evidence

Date: 2026-07-25 America/Los_Angeles
Environment: Windows, Python 3.14
Head before production edits: `32cd4adb`

Command:

`python -m pytest tests/test_api_wiki.py tests/test_wiki_tools.py -q --tb=short`

Result: **17 failed, 133 passed** in 5.27 seconds.

The failures were behavior failures, not collection or fixture errors:

- default search still returned both discovery and coordination matches;
- search, since, exact-read ambient, the public `read_page` wrapper, and the
  256-call reference lacked applied-scope evidence;
- explicit scope was not accepted by the core dispatcher;
- category was ignored;
- exact-read ambient recommendations exposed a restricted candidate's path,
  title, and body under discovery, coordination, and all.

The 256-call dispatcher proof used a non-empty single-threaded reference and
all concurrent raw responses were byte-identical before the missing-scope
assertion failed. No production or plugin-mirror file had been edited.
