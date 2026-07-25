## Context

`subprocess_env_for_provider` currently copies the host environment and subtracts a finite list of known provider variables before applying a universe vault overlay. The repaired denylist closes known partial-overlay and helper-failure paths, but it still inherits direct auth tokens, cloud-provider activation, home/profile discovery roots, proxy credentials, and any future credential variable not yet named by TinyAssets. A helper can also add arbitrary keys to the child. Production mounts maintainer Claude and Codex auth homes, so an incomplete subtraction model can still spend maintainer quota for a user universe.

The function also serves host-local daemon and development calls. Those calls must keep their own subscription authority when no explicit or environment-bound universe exists.

## Goals / Non-Goals

**Goals:**

- Establish universe scope before credential work begins.
- Construct universe provider children from an explicit safe-runtime allowlist, never from a copied host environment.
- Replace home/profile/XDG/temp discovery roots with private universe-owned roots and pin CLI auth homes away from host defaults.
- Admit only validated CA bundle files and recognized selected-provider vault keys; omit ambient proxy authority.
- Fail explicitly if universe credential resolution cannot complete.
- Preserve host-local behavior and keep the canonical runtime and packaged mirror identical.

**Non-Goals:**

- Provider allowlist enforcement, provider/credential receipts, or market matching.
- In-process Gemini, Groq, or Grok client credential resolution; those providers still require a separate fail-closed change before the platform-wide P0 can close.
- Network sandboxing or universal managed-identity metadata isolation.
- Adding credentials, compute, or fallback capacity supplied by TinyAssets.
- Changing API-key opt-in policy or credential-vault storage.

## Decisions

### Determine authority scope before applying credentials

The provider environment builder treats any non-empty explicit `universe_dir` or copied `TINYASSETS_UNIVERSE` binding as universe scope without requiring that path to exist or validate first. When neither binding is present, it returns the normal host-local environment without importing or invoking a vault helper. This prevents a missing/malformed universe path or helper failure from reclassifying a user call as host-local.

Alternative considered: infer scope after the overlay by comparing values. Rejected because a legitimate partial overlay makes value comparison unable to distinguish universe authority from inherited host authority.

### Build the universe child from an empty allowlisted base

For a universe-scoped call, the builder starts with an empty dictionary. It may inherit only execution basics: `PATH`; Windows process bootstrap variables; locale, timezone, and terminal variables; and a small set of CA bundle file variables whose values resolve to absolute existing regular files. `LC_*` is admitted as a prefix family. Proxy variables, `NODE_OPTIONS`, `SSL_CERT_DIR`, and every unrecognized variable are absent. `AWS_EC2_METADATA_DISABLED=true` is forced rather than inherited.

The builder creates `<universe>/.runtime/provider-child/<provider>/home` and `tmp` roots with best-effort `0700` modes. `HOME`, `USERPROFILE`, AppData, XDG, and temporary-directory variables point only under those roots; Windows drive/home-path variables are derived only for a normal drive-letter path. `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are pinned to universe-owned `.credentials` roots before the overlay.

Alternative considered: expand the known-variable denylist. Rejected because a future CLI credential variable would reopen the same maintainer-authority leak. Alternative considered: inherit proxy variables. Rejected because proxy URLs are routing authority and may carry host credentials; authenticated enterprise routing needs an explicit future network-capability surface rather than ambient inheritance.

### Admit only recognized selected-provider vault output

The credential helper receives an empty overlay dictionary, not the child environment. Claude may return only `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY`; Codex may return only `CODEX_HOME` and `OPENAI_API_KEY`. The builder rejects unknown keys or non-string outputs with the same sanitized credential-resolution failure used for helper errors, then updates the safe child environment. This preserves a selected universe's legitimate overlay without allowing a helper regression to reintroduce ambient authority.

### Convert unexpected universe credential failures into an explicit provider failure

Every exception during universe-scoped environment construction or credential overlay becomes a sanitized `ProviderUnavailableError` without underlying exception text, credential values, explicit exception chaining, or retained exception context. Host-local calls do not import or invoke the vault overlay and retain their existing environment under the normal API-key opt-in policy.

Alternative considered: swallow failures after removing host auth. Rejected because silent absence obscures a broken authority path and conflicts with the project's fail-loud rule.

## Risks / Trade-offs

- **Previously working but unauthorized calls will fail** — This is the intended breaking security correction; operators must configure universe-owned authority. Market authority remains separate and unbuilt in this slice.
- **Enterprise proxies are not inherited** — This is intentional. A later explicit network-capability/sidecar contract may admit validated routing without ambient host credentials.
- **Environment isolation is not a network sandbox** — Cloud-route activation and ambient credential files are removed, and AWS EC2 metadata lookup is disabled, but this slice does not claim to block every managed-identity metadata endpoint. Network egress isolation remains separate.
- **A vault helper regression can stop universe inference** — Scope is established without the helper, and focused tests cover explicit and environment-bound universe calls.
- **Runtime and packaged plugin can drift** — Make the same minimal edit in both files and run byte-parity checks.

## Migration Plan

1. Add failing regression tests for ambient direct/cloud/future authority, home/profile discovery, proxy/temp isolation, CA validation, arbitrary overlay keys, and unexpected overlay failure.
2. Implement the allowlisted safe child environment and explicit failure in the canonical runtime.
3. Apply the identical implementation to the packaged runtime mirror.
4. Run focused and surrounding provider tests, strict OpenSpec validation, and mirror parity checks.
5. After the active canonical credential-vault writer releases that file, sync the proven requirement into the canonical spec and archive this change in the same merge lane.

Rollback is a normal revert, but it reopens a maintainer-credential leak and must restore the P0 concern immediately.

## Open Questions

None for this slice. Provider selection, audit receipts, explicit enterprise proxy capability, and network metadata isolation remain separate work.
