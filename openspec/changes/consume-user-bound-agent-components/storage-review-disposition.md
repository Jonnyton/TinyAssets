# Frozen storage review disposition — 2026-09-19

Fable 5.1 session 8636 completed exit 0 after 453 seconds: **APPROVE** exact
2ca96c5256ba68c497e128b7144ffabf23f6cbe9 against parent
493bd98c52609e0b2f16234310c75b8d96f8e46f. Root and implementation owner read the
complete substantive response, preserved in `storage-code-review.md`. The peer
used read-only git-show and ran no tests/children. Approval is dark integration,
not public consumer release, model parity or live user acceptance.

- Atomic reservation, stable intent, source-before-snapshot checks, pair/flag
  crash dedupe, deletion/reset fences, lock order and fixture corrections agreed.
- Orphan sweeper exemption/guarded lifecycle is a real integration dependency;
  root assigned the existing read/startup seam to the file worker. No consumer
  launch queue, independent claim or early orphan inference will be added.
- Supplied-connection scope factory is required before worker integration; it
  must consume existing author/runs transactions without reacquiring maintenance
  or author locks. Schema initialization and producer metadata remain unwired.
- NULL/empty source visibility: root requires compatibility with existing
  `_resolve_readable_branch` (`visibility or 'public'`). Narrow parity follow-up
  needs explicit legacy-public/private-foreign tests. This follow-up is NOT part
  of the reviewed commit and will receive integrated-head verification.
- Malformed completed output normalization to TerminalUnavailable is optional
  hardening, not a release blocker; preserve loud/held behavior meanwhile.
- A non-reset purge during pair-write/flag gap has no current production path;
  any future history-purge API must preserve/invalidate the durable identity.
- Missing post-witness admissions deliberately block recovery. Do not attempt
  automatic destructive repair. An operator must preserve evidence, establish
  exact row identity/cause, and use a separately reviewed repair; the platform
  stays fail-closed until existing recovery can finish. No new repair command is
  authorized by this change.
- Linked runs DB exception-vs-blocker presentation is optional consistency work;
  both paths refuse. No home operational DB deletion authority is expanded.

Selection-parser and later shared/model/public adapter work after 2ca96c52 is not
covered by this approval. Keep exact-head scope and all unshipped limitations
truthful; no private user workflow/design was edited for this proof.
