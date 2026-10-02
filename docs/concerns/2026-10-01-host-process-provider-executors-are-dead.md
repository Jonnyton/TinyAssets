---
severity: P3
title: Four built-in provider executors can never run, and two of them carry vendor SDKs
filed: '2026-10-01'
summary: '`gemini_provider`, `groq_provider`, `grok_provider` and `ollama_provider` declare `credential_source = "host_process"`, and `owner_binding.require_owner_bound_dispatch` refuses every such executor before launch (Hard Rule 15), so none of them can ever serve a call. Gemini and Groq import vendor SDKs (google-genai, groq) and quote stale free-tier limits. Users already reach the same vendors through `api_key_http` and the bundled OpenAI-compatible free-source presets. Delete them; the deletion touches about 25 code and test files, too many for a small PR.'
---

# Four built-in provider executors can never run

**Filed:** 2026-10-01
**Verified:** 2026-10-01, Windows, origin/main `2fe2431b`. The claims come from code reads; the exact lines are cited below.
**Severity:** P3. This is dead weight and a vendor-neutral-compute violation, not an outage.

## What is true

- These four executors declare `credential_source = "host_process"`: `tinyassets/providers/gemini_provider.py`, `groq_provider.py`, `grok_provider.py` and `ollama_provider.py`.
- `tinyassets/providers/owner_binding.py` (`HOST_PROCESS_CREDENTIALS`, and the `require_owner_bound_dispatch` docstring) refuses every such executor immediately before launch. The router is the only code that calls `BaseProvider.complete`, so none of the four can serve a call.
- `owner_binding` names what an owner does instead: connect the source as their own `api_key_http:<definition>`. `tinyassets/providers/free_source_presets.json` already bundles Gemini and Groq as OpenAI-compatible sources. Groq's preset uses `https://api.groq.com/openai/v1`.
- Gemini and Groq import vendor SDKs, which the vendor-neutral compute rule forbids: `google-genai` and `groq`, in pyproject extras at lines 120 and 125. Their docstrings quote free-tier limits that are stale ("14,400 RPD").
- They are still registered and still listed by name:
  - `providers/call.py` `_build_fallback_router`, `fantasy_daemon/__main__.py`, and the `fantasy_daemon/api.py` host-key endpoint;
  - `router.FALLBACK_CHAINS`, `providers/quota.py`, `preferences.py` and `domains/fantasy_daemon/phases/reflect.py`;
  - shims in `fantasy_daemon/providers/`;
  - `.github/channel-specific-baseline.txt`, `deploy/docker-entrypoint.sh`, `deploy/retire_platform_llm_logins.sh`, the `Dockerfile`, and `docs/reference/environment-variables.md` (`GEMINI_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY`).
  - About 20 test files reference them, including `test_platform_has_no_llm.py`, which builds spies from these classes.

## Resolution

Do it as one deletion PR. It is mechanical, with no rerouting, because the OpenAI-compatible path already exists.

1. Delete the four executor modules, their `fantasy_daemon` shims, and their registrations.
2. Remove their names from the fallback chains, the quota table, preferences and the reflect weights.
3. Delete the host-key endpoint branches in `fantasy_daemon/api.py`.
4. Drop the SDK extras from pyproject and the env-var rows from the docs.
5. Update the specs `provider-routing` and `credential-vault` where they name these executors.
6. Rewrite `test_platform_has_no_llm` to spy on the remaining built-ins.

Before deleting, check whether `ollama-local` should stay as an owner-run local source; if it should, give it an owner credential path instead. Delete this file in that PR.
