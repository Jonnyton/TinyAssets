# The host backup's broad GitHub token is readable inside the container

**Filed:** 2026-09-25 · **Verified:** 2026-09-25 against production `1238502d` · **Severity:** P1

## Finding

`/etc/tinyassets/env` still defines `GH_TOKEN`: 40 characters, `gho_` prefix, which is a GitHub
CLI OAuth token. On 2026-09-25 `GET https://api.github.com/user` with it returned 200 and scopes
`gist, repo, workflow`. It is not the founder's local `gh` token (sha256 prefixes differ).

- **Only the host backup job needs it.** `deploy/backup.sh` → `scripts/backup_ship_gh.py`
  uploads nightly snapshots to `Jonnyton/tinyassets-backups` (last success 2026-09-25 03:08Z).
- **Every container in the compose project gets it anyway,** because `/etc/tinyassets/env` is the
  compose `env_file`.
- **The entrypoint strip is not a boundary.** `deploy/docker-entrypoint.sh` unsets `GH_TOKEN`
  before starting the daemon, so the daemon (pid 7) and engines show 0 such variables. But pid 1
  (`tini`) keeps it, and runs as the same `tinyassets` user. As that user,
  `/proc/1/environ` contains `GH_TOKEN=`: the grep count was 1.

So any unjailed code running as the daemon user can read a token that can push to every repository
the founder owns. This is exactly the platform-held push credential the founder ordered removed on
2026-09-24 (Hard Rule 3 / 15 context; "the faster we remove the now security gap the better").
Jailed provider subprocesses (#3958) run in their own PID namespace and are believed not to see
container pid 1, but that hasn't been proven with a test.

`TINYASSETS_GITHUB_PUSH_CAPABILITIES` has already been removed from the env file by #3975/#3976. It
remains only in the running container's pid-1 snapshot, which drops at the next recreate.

The 14 `/etc/tinyassets/env.bak*` files on the host also still contain both values.

## Fix shape

1. **Scope the credential to the job.** The backup gets its own credential, a fine-grained PAT with
   Contents read/write on `Jonnyton/tinyassets-backups` ONLY, in a host-only file the backup unit
   reads (not the compose `env_file`). Earlier attempt: the #3966 round-2 finding that a
   `chown root:root /etc/tinyassets` breaks deploys. Put the file beside the others, not by changing
   ownership of the directory.
2. **Revoke the old token.** Revoke the `gho_` token individually through GitHub's credential
   revocation API (`POST /credentials/revoke`), which does not log the founder's own `gh` out.
3. **Scrub the backups.** Remove `GH_TOKEN` / `TINYASSETS_GITHUB_PUSH_CAPABILITIES` from the
   `env.bak*` files, or delete the backups once their unique content is inventoried (Hard Rule 13).
4. **Make it a guarantee.** Add a test or invariant that the container `env_file` carries no
   credential the daemon doesn't use.

Steps 1 and 2 need the founder (credential creation and revocation): see `docs/host-actions.md`.
