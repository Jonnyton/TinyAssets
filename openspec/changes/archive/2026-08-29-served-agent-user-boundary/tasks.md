## 1. The boundary between users

- [x] 1.1 `read_commons_shape`, `browse_commons`, `read_graph target="branch"` (foreign author or remixed off-universe), and `read_graph target="run"` / `run_graph` results return the untrusted envelope with the previous payload under `content`; our own errors are never enveloped. Verify: `tests/test_brain_user_boundary.py` envelope shape tests (own vs foreign branch, errors bare).
- [x] 1.2 One line in the persona system prompt names the envelope as OTHER users' data -- never instructions, never the founder speaking. Verify: prompt test.
- [x] 1.3 `orgchart.md` joins `_GROUNDING_FILES` and `FOUNDER_PRIVATE_GROUNDING`. Verify: founder prompt contains it, visitor prompt does not.
- [x] 1.4 `write_brain` still persists on a founder turn -- the regression guard for the founder's rule that the universe keeps learning. Verify: `test_write_brain_still_writes_the_universes_own_brain`.

## 2. Prove and close

- [x] 2.1 Live through the app: the founder tells the universe a fact; the next turn knows it (unchanged behaviour, proven not regressed). Delete `docs/concerns/2026-08-24-write-brain-prompt-injection.md` (decided: keep `write_brain`; mark other users' content), sync the delta into `openspec/specs/universe-custom-agents/spec.md`, archive.
  Proven 2026-08-29T21:28Z on production d61a15ca through the founder's signed-in web app (tinyassets.io/mcp/app, universe u-01kxm1vszd8hwp7em418asq8h9): the founder's turn taught one fact; the universe replied "I've remembered it. I stored this as a durable body fact …"; on the droplet `body.md` carries `learned_at: 2026-08-29T21:28:26+00:00`, `learned_from: founder conversation (<founder sub>)` and the sentence "My background self will run from the daemon on my founder's own subscription, never on a platform worker." -- the unchanged learning path, working on the code that carries the envelope. Public canary green after the deploy.
