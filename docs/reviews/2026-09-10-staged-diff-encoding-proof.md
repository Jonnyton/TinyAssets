# Staged Python diff checker: isolated fix proof

September10,2026,04:24UTC. Branch codex/check-staged-diff-encoding,
base2d12f84661f2fb9b3c6c0d9609456f3b3715319f. Extracts only the checker and its
tests from existing primary92ad462d, excluding unrelated cross-user-node work.
Adds one real-Git subprocess regression beyond that existing patch.

Old code requested locale-decoded subprocess text and treated unreadable/missing
output as an empty successful diff. New code captures bytes, decodes UTF-8 with
surrogateescape, and returns failure on Git/pipe acquisition errors. The forbidden
import grammar is unchanged. Invalid source bytes remain inspectable, not erased.

Baseline Windows:18passed. New real-Git test was run against the exact old main
checker before restoring the patch: it failed as expected, showing a cp1252
reader-thread UnicodeDecodeError on byte0x90 while the checker exited0. The fixed
checker exits2 and names the forbidden import, without that decoding traceback.
Temporary repositories are created by pytest outside the project; no user file
or real project index is used by that test.

Verification commands, September10 Windows Python3.14 / actual Ubuntu Docker
Python3.11.16,git2.47.3,bubblewrap0.12.0:

```
python -m pytest -q tests/test_pre_commit_invariant_author_server.py --tb=short -rs
python -m ruff check scripts/pre_commit_invariant_author_server.py tests/test_pre_commit_invariant_author_server.py
```

25Windows passes,0skips,0.50s;25actual Linux passes,0skips,0.16s via the reviewed
scripts/linux_oracle.py harness. Linux snapshot preparation took minutes while
copying the source tree; the confirmed running container was allowed to finish,
not restarted due to an observation timeout. Ruff and diff checks pass.

No canonical runtime, public API, storage, workflow, provider binding, credential
or user permission changes. No daemon mirror rebuild required. This corrects a
developer delivery gate; an app conversation cannot exercise staged Git input.
Do not spend another workflow retest to claim proof of this checker. Current
live app evidence remains the2d12f84621:03PDT retest documented separately.

Independent exact-head review and CI are pending. Rollback is normal revert of
this isolated tooling commit if a legitimate Git diff is falsely rejected;
never disable the hook or treat a read failure as successful verification.
