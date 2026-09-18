# Bootstrap/deletion non-blocking follow-ups

**Filed:** 2026-09-18
**Verified:** Claude Fable read-only shape review, session
`0e56edbd-fb91-4385-93e0-7a82d6a3590d`; code inspected on the
`recover-openrouter-key-handoff` branch. These were explicitly non-blocking
hardening, separate from the secret-bearing vault resurrection race addressed
by the same change's shared guard and Windows/Linux barrier regressions.

## Source (verbatim)

> **DISAGREE_CONCERN, note in design only.** `_gesture_lock` is a process-local lock at `serving.py:65`. It is authoritative only for a single-process daemon. Deploy sets no `--workers`, so it holds today, and OAuth already inherits this.

> - `_file_lock` mkdir at `provider_assignment.py:964` leaves an empty ghost home plus lock file after deletion for any taker, including shared readers such as `model_options.py:104`.
> - Post-discovery writers `connect_compute`, `create_binding`, `request_from_user` lack in-transaction `check_current_home`. Rows written after the sweep are inert orphans.
> - Drop the redundant mkdir at `credential_vault.py:487`. Every caller already holds the lock that created the directory.
> - First-contact TOCTOU between `first_contact.py:80` and `:96` is inherited by `scope(create=True)`.
> - The writer connection at `credential_vault.py:635` sets no busy timeout. A long deletion sweep makes a concurrent deposit fail closed after five seconds, acceptable but worth a pragma.

## Scope

Do not treat the proposed fixes as implemented or the current process-local
gesture lock as a multi-worker guarantee. Recheck exact call sites before
future work. Preserve same-owner approval, non-home admin credential deposits,
the existing lock order and Windows rename behavior. Follow-up hardening must
not delay the independently reviewed manual acquisition MVP's live acceptance.
