# Consume sandbox mount descriptors before payload execution

September15,2026 UTC. Security prerequisite for workspace-node provisioning;
ordinary workspace launcher is affected independently of that unpublished work.
This repair displaces provisioning integration and contains none of its new API.

## Evidence and repair

Base main8be980c6, local native WSL Docker oracle, Python3.11.16/git2.47.3/
bubblewrap0.12.0. Added test_workspace_handle_is_consumed_before_payload fails
on the unchanged base: payload can fstat the inherited host directory handle.
Ordinary workspace file access succeeds before the failure; this is not a
missing tool/dependency/environment failure. No observed tenant exploitation.

BwrapLauncher now consumes validated mount fds after bwrap mount setup, before
the supplied runner. Isolated Python bootstrap excludes checkout/user startup
imports. It closes exact integer descriptors above standard IO, tolerating only
EBADF, then restores argv and compiles the original runner in a fresh __main__
namespace. Future imports, stdin/stdout/stderr and exit behavior are preserved.
Mount flags, namespace separation, workflow shape and permissions are unchanged.
Launchers without inherited mount descriptors remain byte-for-byte equivalent.

Windows focused cohort:229passed18skipped18.96s. Ruff and generated plugin444files/
import probe pass. Linux final stable-tree oracle remains required before push;
Linux CI, exact-head independent review and live proof remain required to land.

## Review and delivery gate

Fable5.1 shape attempt exited1 after7seconds with no review. A separate minimal
CLI diagnostic returned an explicit selected-model unavailable/inaccessible
message. No quota or account-wide outage established. Founder was asked whether
to use Claude account-default or wait; no alternate model dispatched yet.
This is a new bug review, not a fourth review for held3859/3853. No approval.

Keep any PR draft until exact-head cross-family approval. After normal merge and
deployment, verify deployed SHA plus public canary, then refresh/read the app
and send exactly `Retest your workflow checklist`. Never replay uncertain turns
or edit the user's workflow. Real-user clean use has not been observed for this
unreleased repair. Rollback is normal revert/deploy, with no storage migration.
