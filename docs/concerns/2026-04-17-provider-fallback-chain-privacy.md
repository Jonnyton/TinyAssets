# Privacy Q6.3 - third-party providers remain in the fallback chains

**Filed:** 2026-04-17 | **Verified:** 2026-07-25 | **Re-verified:** 2026-08-25

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

Privacy Q6.3: legacy set_engine writes no ceiling; gemini/groq/grok remain fallbacks
(router.py:89-92), and ambient no-universe env can reach maintainer auth until V2.

## Re-verification 2026-08-25 - line numbers corrected

The row cited `router.py:89-92`. Current locations in `tinyassets/providers/router.py`:

| Line | Content |
|---|---|
| 181 | `"writer": ["claude-code", "codex", "gemini-free", "groq-free", "grok-free", "ollama-local"]` |
| 182 | `"judge": ["codex", "gemini-free", "groq-free", "grok-free", "ollama-local"]` |
| 183 | `"extract": ["codex", "gemini-free", "groq-free", "ollama-local"]` |
| 191 | `"codex", "gemini-free", "groq-free", "grok-free", "ollama-local",` |
| 247 | `{"gemini-free", "groq-free", "grok-free"}` |

Premise holds: user content can reach Gemini, Groq, or Grok through a fallback the user never chose.

## The three clauses are separable

1. `set_engine` writes no ceiling - see the R2-1a work item.
2. Third-party providers remain in the fallback chains - the privacy exposure proper.
3. Ambient no-universe env can reach maintainer auth - overlaps
   `2026-06-30-current-actor-env-fallback.md`.
