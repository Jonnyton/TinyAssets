# Zone validation accepts host-specific names as IANA account zones

Review: PR #4128, requested head b955e79d, base 7261fcb1. P2 portability
correctness, not a demonstrated cross-account write or arbitrary file read.

`tinyassets/schedule_timezone.py:66` accepts everything ZoneInfo resolves.
The exact head module accepts `localtime` and `posixrules` in the installed
Linux oracle image (230e3656cb05), but rejects both on this Windows host.
`localtime` refers to host clock configuration, not a portable owner's zone.
The account setter stores these accepted strings unchanged. On a host where
they no longer resolve, account_timezone.py:112 returns empty and later creates
fall back to UTC; an existing cron with such a zone raises in due selection.

Restrict account/automation zones to portable timezone identifiers, or define
and enforce a normalization contract for system-specific aliases.

Negative checks passed: absolute/traversal paths, NUL, blank, whitespace,
10000-character names and non-string JSON were refused; previous account value
survived. Handler returned 401 without identity and 403 for another origin.
Supplying owner_user_id='b' while signed in as 'a' changed only a's timezone.
