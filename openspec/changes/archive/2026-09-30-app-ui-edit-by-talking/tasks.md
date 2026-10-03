# Tasks: app UI edit by talking

Owner: claude-code. One PR.

- [x] Storage: `change_app_ui_entry` -- one targeted change, compare-and-set on the row, re-applied on a lost race
- [x] Handles: connector + engine `write_graph target="app_ui"` operations; compact `read_graph` reads
- [x] Engine: `read_graph target="app_ui"` defaults to the index; `read_brain section=`
- [x] Handbook `interfaces` chapter: one UI at a time
- [x] App: `AppUI.turnSettled` after every delivered turn
- [x] Tests: large library through the served path, cross-user, lost update, etag, harness section, app refresh
