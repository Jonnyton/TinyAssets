# Independent review: drain image inspection output

2026-09-24 UTC; Codex root independently reviewed Claude-authored two-line
workflow change and tests/test_deploy_digest_stream_drain.py on
codex/digest-stream-drain, based on ff1320d5. Verdict: APPROVE for shape and
basic safety. Final immutable head is named in the PR approval body.

Both digest readers now print only the first top-level Digest line while
consuming the rest of the producer's output. Previously awk exited early,
which can break the upstream pipe and fail deployment under pipefail.
The failed35947947560 run is consistent with this hazard, not definitive proof
of that run's cause. The fix changes neither image selection nor validation,
credentials, SSH, ancestry checks, deployment ordering or rollback behavior.

Root Windows/Python3.14/Git Bash verification at02:55–02:56UTC:

- `python -m pytest tests/test_deploy_digest_stream_drain.py -q -p no:cacheprovider
  --basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-root-digest-review`:
  16passed0skipped,3.29s. Real large bash producer reproduces old early-close
  failure; both extracted corrected programs drain it successfully. First-match
  selection and the actual production validator's rejection paths are covered.
- `python -m ruff check tests/test_deploy_digest_stream_drain.py`: clean.
- `C:/Users/Jonathan/AppData/Local/Temp/ta-actionlint/bin112/actionlint.exe
  .github/workflows/deploy-prod.yml .github/workflows/recovery-retag-image.yml`:
  exit0. `git diff --check`: clean.

Local checks do not replace required hosted CI or a subsequent live deployment
through the modified workflow. No Docker/WSL, local service or production
execution occurred. Do not rerun older6918a05a deployment over ff1320d5.
Rollback is reverting the two extraction expressions; it does not roll back
the deployed application. Broader platform capabilities remain open.
