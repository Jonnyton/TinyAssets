## Context

`subprocess_env_for_provider` currently copies the host environment and subtracts a finite list of known provider variables before applying a universe vault overlay. The repaired denylist closes known partial-overlay and helper-failure paths, but it still inherits direct auth tokens, cloud-provider activation, home/profile discovery roots, proxy credentials, and any future credential variable not yet named by TinyAssets. A helper can also add arbitrary keys to the child. Production mounts maintainer Claude and Codex auth homes, so an incomplete subtraction model can still spend maintainer quota for a user universe.

The function also serves host-local daemon and development calls. Those calls must keep their own subscription authority when no explicit or environment-bound universe exists.

## Goals / Non-Goals

**Goals:**

- Establish universe scope before credential work begins.
- Construct universe provider children from an explicit safe-runtime allowlist, never from a copied host environment.
- Replace home/profile/XDG/temp discovery roots with private universe-owned roots and pin empty CLI auth homes away from host defaults and credential-artifact probes.
- Admit only validated CA bundle files and recognized selected-provider vault keys; omit ambient proxy authority.
- Reject linked, multi-link, non-file, or physically outside vault sources before any public vault resolver reads them.
- Physically contain every runtime and credential path before any directory creation, materialization, or helper side effect.
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

For a universe-scoped call, the builder starts with an empty dictionary. It may inherit only execution basics: `PATH`; Windows process bootstrap variables; locale, timezone, and terminal variables; and a small set of CA bundle file variables whose values resolve to absolute existing regular files. Locale inheritance is limited to explicit POSIX/GNU categories (`LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME`, `LC_ADDRESS`, `LC_IDENTIFICATION`, `LC_MEASUREMENT`, `LC_NAME`, `LC_PAPER`, and `LC_TELEPHONE`), never an `LC_*` wildcard. Proxy variables, `NODE_OPTIONS`, `SSL_CERT_DIR`, and every unrecognized variable are absent. `AWS_EC2_METADATA_DISABLED=true` is forced rather than inherited.

The builder accepts only the exact canonical provider names `claude-code` and `codex` for a universe-scoped child. It canonicalizes the universe directory to an absolute resolved root, then resolves every planned home, profile, XDG, temporary, and empty-auth target before creating any of them. Every resolved target must remain physically beneath the universe root even when existing path components are symlinks, junctions, or reparse points. Only after the complete preflight succeeds does it create `<universe>/.runtime/provider-child/<provider>/home`, `tmp`, and `auth-empty/{claude,codex}` roots with best-effort `0700` modes. `HOME`, `USERPROFILE`, AppData, XDG, and temporary-directory variables point only under those roots; Windows drive/home-path variables are derived only for a normal drive-letter path. Default `CLAUDE_CONFIG_DIR` and `CODEX_HOME` values point beneath `auth-empty`, so ordinary empty setup never creates `.credentials/*` or changes the vault's credential-availability predicates.

Alternative considered: expand the known-variable denylist. Rejected because a future CLI credential variable would reopen the same maintainer-authority leak. Alternative considered: inherit proxy variables. Rejected because proxy URLs are routing authority and may carry host credentials; authenticated enterprise routing needs an explicit future network-capability surface rather than ambient inheritance.

### Admit only recognized selected-provider vault output

Before invoking any public vault resolver or helper, the builder checks `<universe>/.credential-vault.json` with `lstat` semantics. Missing remains the canonical empty-vault case. A present source must be a physically contained, non-symlink regular file with one link; linked, multi-link, non-file, or outside sources fail before runtime or credential artifacts are created. The builder then calls the selected provider's public read-only vault resolver and preflights both its configured/existing auth path and the provider's default `.credentials/<service>` materialization target against the canonical universe root. This rejects an outside target before the helper can create a directory or materialize an auth bundle.

The credential helper receives an empty overlay dictionary, not the child environment. Claude may return only `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY`; Codex may return only `CODEX_HOME` and `OPENAI_API_KEY`. The builder rejects unknown keys, non-string outputs, and auth paths whose resolved physical location is outside the universe, then updates the safe child environment. This post-helper validation detects a helper regression and refuses provider launch, but it cannot undo a hypothetical helper side effect that occurred before the helper returned. The preflight covers every currently reachable helper path before invocation.

This slice validates selected auth-directory locations, not every pre-existing leaf below a physically contained selected directory. Existing contents under such a directory are trusted credential material governed by the universe owner and the same-host filesystem/OS-sandbox boundary. Recursive leaf-symlink scanning is not a substitute for that boundary and is outside this process-environment slice.

### Convert unexpected universe credential failures into an explicit provider failure

Every exception during universe-scoped environment construction or credential overlay becomes a sanitized `ProviderUnavailableError` without underlying exception text, credential values, explicit exception chaining, or retained exception context. Host-local calls do not import or invoke the vault overlay and retain their existing environment under the normal API-key opt-in policy.

Alternative considered: swallow failures after removing host auth. Rejected because silent absence obscures a broken authority path and conflicts with the project's fail-loud rule.

## Risks / Trade-offs

- **Previously working but unauthorized calls will fail** — This is the intended breaking security correction; operators must configure universe-owned authority. Market authority remains separate and unbuilt in this slice.
- **Outside-universe credential paths now fail** — Existing records that point Claude or Codex auth outside the universe, directly or through a symlink/junction/reparse component, must move that material under the universe. There is no compatibility exception because it would restore cross-universe authority.
- **Linked vault sources now fail** — A symlinked, junction/reparse-linked, hardlinked/multi-link, non-file, or physically outside `.credential-vault.json` is refused. Operators must write a private single-link regular vault file directly beneath the universe.
- **Ambient universe bindings scope host tools** — Host tooling that inherits `TINYASSETS_UNIVERSE` receives universe isolation. Host-local tooling must run without that binding.
- **Enterprise proxies are not inherited** — This is intentional. A later explicit network-capability/sidecar contract may admit validated routing without ambient host credentials.
- **Environment isolation is not a network sandbox** — Cloud-route activation and ambient credential files are removed, and AWS EC2 metadata lookup is disabled, but this slice does not claim to block every managed-identity metadata endpoint. Network egress isolation remains separate.
- **Local path preflight has a TOCTOU residual** — The stated path guarantees assume no concurrent same-host link mutation between validation and runtime-directory creation, helper directory/auth-material writes, or later provider filesystem use. A same-host actor with that mutation authority can race path-based checks. OS-backed directory handles and a real process/filesystem sandbox are the full fix; this process-environment slice does not claim them.
- **A vault helper regression can stop universe inference** — Scope is established without the helper, and focused tests cover explicit and environment-bound universe calls.
- **Runtime and packaged plugin can drift** — Make the same minimal edit in both files and run byte-parity checks.

## Migration Plan

1. Add failing regression tests for ambient direct/cloud/future authority, home/profile discovery, proxy/temp isolation, CA validation, arbitrary/outside overlay paths, physical path escapes, malformed vaults, and unexpected overlay failure.
2. Implement the allowlisted safe child environment and explicit failure in the canonical runtime.
3. Apply the identical implementation to the packaged runtime mirror.
4. Run focused and surrounding provider tests, strict OpenSpec validation, and mirror parity checks.
5. After the active canonical credential-vault writer releases that file, sync the proven requirement into the canonical spec and archive this change in the same merge lane.

Rollback is a normal revert, but it reopens a maintainer-credential leak and must restore the P0 concern immediately.

## Open Questions

None for this slice. Provider selection, audit receipts, explicit enterprise proxy capability, and network metadata isolation remain separate work.
