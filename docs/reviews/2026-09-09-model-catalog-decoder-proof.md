# Model catalogue decoding — advisory, no live discovery yet

September 9,2026. Pure protocol-boundary decoding is implemented locally in
providers/catalog_decoders.py. It neither opens a network connection nor grants
inference authority. Connection/account identity, owner-filtering, executor tool
support and snapshot freshness are supplied by a separately verified transport
context; response fields cannot override them.

The [documented OpenRouter user catalogue](https://openrouter.ai/docs/api/api-reference/models/list-models-filtered-by-user-provider-preferences-privacy-settings-and-guardrails)
is normalized into opaque model ids, explicit input/output modalities, tool
support, conservative advertised context and component-specific integer pricing.
Optional unfamiliar non-authority fields are ignored; duplicate/invalid ids and
known partial pagination fail loudly without following returned URLs. A changed
data list admits a newly named model without a compiled release list. Missing,
invalid, unrepresentable or unfamiliar charge evidence never becomes free.
Only the documented prompt/completion/request/image pricing subset is supported
in this decoder so far; an additional charge component marks pricing unknown.
That limitation must be resolved against real account responses and matching
dispatch price enforcement before full automatic selection is claimed.

The [benchmark response](https://openrouter.ai/docs/api/api-reference/benchmarks/list-benchmarks)
is restricted to one comparable source, uses exact indices and its reported
as_of time rather than the latest fetch time. Duplicate per-model records are
unranked. Only exact model ids or an explicitly declared canonical slug can
join scores; no guessed display-name matching or stripping a free suffix.
This is documentation/fixture evidence, not confirmation of a live account join.

The advisory policy now checks required output modalities independently of
input modalities and tool support. Legacy constructed Model/Interaction values
keep the prior text-output default; missing remote output evidence is explicit.

Verification, September 9,21:24 UTC:

- `python -m pytest -q tests/test_catalog_decoders.py tests/test_model_policy.py`:
  76 passed on Windows Python3.14.
- Same command plus tests/test_mirror_parity_gate.py:91 passed,4.29s on Windows.
- Supplemental Ubuntu Python3.11.15, same three files through the existing
  external-temp output/receiver-linux-proof.sh:91 passed,13.86s, no skips; one
  pre-existing LangChain deprecation warning. Not a Docker-oracle claim.
- Ruff checks and formatting passed; plugin build mirrored399 runtime files
  and passed the import probe; git diff --check passed.

Required next work: bind discovery profiles to accepted connection configuration,
read through the exact credential-blind scoped proxy with live owner/grant and
endpoint checks, retain freshness/cache/error provenance, enforce cost at dispatch,
integrate per-attempt selection and actual tools, then the usable UI and live
rendered acceptance. Independent integration review is still required. No app
or MCP caller uses these decoders and no private workflow/grant was changed.
