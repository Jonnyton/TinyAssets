# Build a signed Android App Bundle without CI

This is the route that put the app on Google Play on 2026-09-03. It exists because
`gh secret set` is denied to the agent harness, so the four `ANDROID_UPLOAD_*` repo
secrets that `android-release.yml` needs may not exist — but GitHub secrets were only
ever *one* route to a signed bundle, not the goal. This container mirrors the
workflow's own steps and needs **no GitHub repository secrets**. It takes about five
minutes.

It is not credential-free, and the distinction matters: signing still consumes the
real upload keystore and both of its passwords, read from `~/.tinyassets/android`
mounted at `/keys` read-only. Anyone who can run `sign.sh` can sign as you. What this
route removes is the need to copy those values into GitHub, not the need to hold them.

Prefer `android-release.yml` when the secrets do exist. Use this when they do not,
when you want to reproduce a CI failure locally, or when you need a bundle now.

## Run it

```bash
# from the repo root; MSYS_NO_PATHCONV stops Git Bash mangling container paths
docker build -t ta-android-build:local mobile/container

MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd):/work" -w /work \
  ta-android-build:local bash /work/mobile/container/build.sh

MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd):/work" \
  -v "$HOME/.tinyassets/android:/keys:ro" \
  -w /work ta-android-build:local bash /work/mobile/container/sign.sh
```

The signed bundle lands at `mobile/tinyassets-release.aab`, which `mobile/.gitignore`
already covers, so it cannot be committed by accident.
Upload it in Play Console → Test and release → the track you want → Create new
release → Upload. The Console's file input takes the `.aab` directly.

## What the toolchain pins, and why each number matters

| Pin | Why |
|---|---|
| Android platform **36**, build-tools **36.0.0** | Play has required `targetSdk` 36 of new apps since 2026-08-31. A lower target is **rejected at upload**, not warned about. |
| **JDK 21** | Capacitor 8 compiles its Java at source/target 21. JDK 17 dies with `error: invalid source release: 21`. |
| **node 22** | `@capacitor/cli@8` declares `engines.node >= 22.0.0`. |

These match `android-release.yml` deliberately. If you change one there, change it
here, or this stops being a faithful mirror and starts being a second opinion.

## Two things that will bite you

**`build.sh` moves `mobile/android` aside first, on purpose.** `cap add android`
refuses to overwrite an existing platform, and — worse — `cap sync` *preserves* a
stale `android/variables.gradle`. A tree generated under Capacitor 6 therefore keeps
`minSdkVersion = 22` and compile/target 34 even after the dependency bump, and builds
a bundle Play rejects while looking perfectly healthy. CI never hits this because it
always starts from a clean checkout.

It **moves** rather than deletes, to `mobile/android.superseded.<timestamp>` (also
gitignored), and prints where it went. The container runs against a bind-mounted
repo, so a delete here is a delete on your machine — and while that directory is
generated and gitignored, gitignored is not disposable: native customization you
have not committed exists on no remote and in no history. Clearing the snapshots is
your call, not the script's.

**`sign.sh` strips carriage returns from `upload-keystore.env`.** That file was written
on Windows, so sourcing it directly leaves a trailing `\r` on every value and keytool
reports `Keystore was tampered with, or password was incorrect` — which sends you
hunting a corrupt keystore instead of a line ending. The same trap applies to
`gh secret set`; see `docs/host-actions.md`.

Signing fails closed: it verifies the keystore's certificate against the SHA-256
pinned in `android-release.yml` before it signs anything, and refuses on mismatch.

## After it runs

`npm ci` inside the container leaves `mobile/node_modules` holding **Linux** binaries.
That is harmless for the container but will confuse a local Windows `npm run` — run
`npm install` in `mobile/` to restore it if you work there.
