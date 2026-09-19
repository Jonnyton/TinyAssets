# In-node delivery verification (in progress)

2026-09-19, local Windows worktree based on proposal commit
`f001450fcaa4105c00b164a175339fb382b71267`, uncommitted implementation.
This is not exact-head release approval or live-user acceptance.

## Red-first and current boundaries

- The first new subprocess RPC test failed because `_prepare_run` did not accept
  trusted `owner_user_id`. Explicit owner plumbing and RPC acceptance were then
  implemented under the recorded RPC shape approval.
- The actual nested invocation test then failed with uniform child-unavailable:
  run actor `universe:u-sender` differs from the owned private child's author
  `sender`. This additional authority rule is documented separately and remains
  unimplemented pending focused pre-build review.
- Eleven cases (nested success plus ten private-child refusal cases) are
  deliberately incomplete gates, not passing coverage.

## Linux baseline comparison and sandbox proof

The canonical `python scripts/linux_oracle.py -- -q
tests/test_delivery_node_rpc.py -k 'not nested_invoke and not owned_private_child'`
could not launch: the Windows Docker Desktop pipe was absent. A working existing
WSL Ubuntu Docker engine was used instead; this is fallback evidence, not a claim
that the canonical wrapper passed.

Image `tinyassets-workspace-browser-probe:e2d3edcc`, immutable local ID
`sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`:
Python 3.11, git and real bubblewrap. No browser/user account was used. Container
options: `--rm --network=none --memory=2g --pids-limit=1024
--security-opt seccomp=unconfined`; readonly working-tree source mount at `/src`,
`PYTHONDONTWRITEBYTECODE=1`, `TMPDIR=/tmp`, pytest cache disabled.

Initial candidate run: 157 passed, four failed, eleven deselected. All four were
existing `test_run_branch_version.py` handler tests trying to initialize
`/.tinyassets` under the image's nonroot user. An unchanged `git archive` of
`f001450f`, extracted only into a disposable container, reproduced the exact four
failures (14 passed). Setting the documented data root to disposable
`TINYASSETS_DATA_DIR=/tmp/tinyassets-test-data` gave baseline 18/18 passed.
No runtime workaround or test weakening was added.

With the same explicit disposable data directory, the candidate command was:

```text
python -m pytest -q -p no:cacheprovider tests/test_delivery_node_rpc.py
tests/test_delivery_public.py tests/test_delivery_runtime.py
tests/test_node_enqueue_verb.py tests/test_sub_branch_invocation.py
tests/test_run_branch_version.py
-k 'not nested_invoke_uses_child and not owned_private_child' --tb=short
```

Result: **161 passed, 11 deselected, zero skipped**, 30.56 seconds. Includes
`test_real_linux_jail_transports_delivery_rpc` using actual `BwrapLauncher` and
the subprocess cancellation check after RPC read but before acceptance.

Final candidate must run all eleven pending cases and the invoke regressions,
refresh plugin mirrors, pass lint, and receive independent exact-code review.
Production deployment and ordinary rendered two-owner acceptance remain separate
root-owned gates. Files, receiver retry and retention remain outside this slice.

## Reviewed authority adaptation implemented; pre-integration results

After the focused ADAPT review and parent approval, thirteen private-child cases
were run red-first: all failed on the missing context field or call parameter.
The reviewed same-definition-author restriction and uniform run-read refusal were
then implemented. These results supersede the earlier pending-test status but do
not substitute for post-main-integration or exact-head release evidence.

- Windows Python 3.14: complete six-file RPC/public/runtime/enqueue/sub-branch/
  version group **174 passed, 1 skipped** (real Linux-only bubblewrap).
- Windows carried-approval, node-reuse and invoke-authoring group **44 passed**.
- Linux fallback container, same explicit disposable configuration above, all
  nine files together: **219 passed**, no skips or deselections, 54.94 seconds.
- `python -m ruff check` on all five changed canonical modules and the new test
  passed; `git diff --check` passed. Plugin builder staged 464 files and its
  import probe returned `probe-ok`.

Ordinary main integration and final exact-code review are next. No live user
graph/account or production action was performed.
