# OTVDM Runtime Adapter Patch Request

**Status:** proposed patch triage. Not canonical architecture until accepted into `PLAN.md`.

**Source request:** WIKI-PATCH / Issue #342, `PR-030 (proposed) ADAPTER-OTVDM-001: otvdm-v1 runtime adapter`.

## Classification

Patch request. The request proposes a new runtime adapter for the early-Windows freeware corpus, not a bug fix.

## Decision Boundary

The adapter is a candidate host-side runtime, not a browser-only exact-game success path yet.

The existing classic-game contract still applies:

- Prefer lawful original media in a browser runtime.
- Do not bundle proprietary Microsoft Windows 3.x files, DLLs, fonts, or disk images.
- Label any desktop helper path as a host/runtime adapter, not as zero-install chatbot play.
- Do not treat a nonblank launcher, install success, title screen, or shell as playability proof.

OTVDM/winevdm is relevant because the upstream project is GPL-2.0 licensed and describes itself as a way to run 16-bit Windows applications on 64-bit Windows. Its README also describes Wine-based Win16-to-Win32 conversion code, CPU/DOS emulation pieces, and incomplete DOS emulation with DOSBox recommended for DOS executables:

- <https://github.com/otya128/winevdm>
- <https://github.com/otya128/OTVDM>

That does not by itself clear every game. Each target title still needs its own lawful freeware/shareware/original-media status and a compatibility proof.

## Minimal Accepted Scope

An `otvdm-v1` adapter can be accepted only as a narrow host capability with these constraints:

1. Runtime source is pinned to an upstream release or source revision with GPL-2.0 license attribution.
2. The repository stores no Microsoft Windows 3.x operating-system media and no proprietary game media.
3. The adapter accepts only per-title media that is freeware, shareware-redistributable, public-domain, or user-provided.
4. The launcher records the title, media source, media license/distribution status, adapter version, host OS, and exact command line used.
5. The adapter reports branch states separately from browser runtime states:
   - `HOST_ADAPTER_PLAYABLE`
   - `NEEDS_HOST_RUNTIME`
   - `NEEDS_RIGHTS_CLEARED_MEDIA`
   - `NEEDS_USER_MEDIA`
   - `INCOMPATIBLE_WITH_OTVDM`
6. The result is advertised to chatbot users as a daemon-host execution path unless a later browser-compatible Win16 runtime exists and passes the browser proof gate.

## Verification Gate

The first implementation must prove one rights-cleared Win16 freeware title end to end:

- clean adapter install or build on a supported daemon-host OS;
- media source and license captured in repo docs or generated run metadata;
- launch reaches real gameplay, not only a desktop window or title screen;
- user-facing input changes game state;
- audio path is documented and verified when the target uses audio;
- logs distinguish runtime failure, media/license blocker, and game incompatibility;
- no proprietary Microsoft OS files are downloaded, generated, cached, or committed.

Because this adapter would execute old binaries on a host, the implementation also needs a sandboxing/security pass before it can be exposed to paid or community daemon queues.

## Non-Goals

- Shipping a Windows 3.x image, registry hive, or bundled system directory.
- Replacing browser-first exact-game proof for chatbot users.
- General DOS game support. Upstream explicitly recommends DOSBox for DOS executables.
- Treating GPL compatibility as solved for downstream packaging without review.

## Next Small Build

Add a host capability detector and dry-run manifest format first. It should answer "can this daemon attempt OTVDM jobs, and with which adapter build?" without executing arbitrary user media. The first executable slice should stay behind an explicit host opt-in and target one rights-cleared test title.
