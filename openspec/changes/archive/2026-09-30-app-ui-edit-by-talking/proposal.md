# Change a person's UI by talking: one UI at a time

## Why

Live 2026-09-30 the founder asked their universe "is the GTM Village done? lets
try it out". It replied that it could not switch the screen because its UI read
"still cuts off before the revision needed to save that change safely". The only
write on `target="app_ui"` was a whole-row compare-and-set: read the entire
library, edit it, send it back with the revision. A universe works through a
model whose tool results are bounded (`engine_result_bounds`), so a library
larger than one result could never be switched or edited by talking.

## What changes

- `write_graph target="app_ui"` gains targeted operations that name ONE UI or
  only the choice and take no revision: `activate`, `use_default`, `add_ui`,
  `replace_ui`, `edit_ui` (whole fields and/or exact once-only text edits),
  `remove_ui`. Each is atomic on the stored row and never overwrites a
  concurrent change; `expected_etag` optionally pins the version of one UI.
- `read_graph target="app_ui"` reads compactly: `query="index"` lists ids, names,
  etags and field sizes with no bodies; `query=<ui_id>` reads one UI;
  `field_name` + `output_offset` pages one field. The universe's engine surface
  reads the index by default and never the whole library.
- The app re-reads the row after each finished turn when its revision moved, so
  an activation made by talking shows without a reload.
- `read_brain` (the universe's harness) takes `section` to read one section.

`save` is unchanged. No new target, no new handle: the canary's handle set is
the same.
