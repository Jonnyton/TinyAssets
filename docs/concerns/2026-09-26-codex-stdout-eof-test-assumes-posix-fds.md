# The codex stdout-EOF watchdog test assumes POSIX fd semantics and is red on Windows

**Filed:** 2026-09-26
**Verified:** 2026-09-26, local Windows, Python 3.14, repo venv — command and output below
**Severity:** P2 — a dev-box-only red that is not in the known-failing list, so every
lane that touches this area has to re-diagnose it

`tests/test_codex_stream_watchdog.py::test_stdout_eof_with_a_live_child_ends_the_child_and_leaks_no_task`
fails on a Windows dev box, **in isolation**, on a tree whose only changes are
elsewhere. It is not in `.github/known-failing-tests.txt`, so it reads as a
regression to whoever runs into it.

## Repro

```
python -m pytest "tests/test_codex_stream_watchdog.py::test_stdout_eof_with_a_live_child_ends_the_child_and_leaks_no_task" -q
```

→ `1 failed`. The chain:

```
tinyassets/providers/codex_provider.py:606: in _stream_codex_exec
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=budget)
asyncio.exceptions.CancelledError -> TimeoutError
tinyassets.exceptions.InteractiveDeadlineError: codex exec exceeded the 5s
absolute interactive cap while still progressing
```

## Why it is the test, not the runtime

The test's child is:

```python
sys.stdout.write(json.dumps({'type':'thread.started'})+'\n'); sys.stdout.flush()
os.close(1); time.sleep(30)
```

It asserts that closing **fd 1** while the process keeps running gives the parent
EOF, so the reader can end the child (`rc is not None`) inside a bounded grace
(`elapsed < 15`). That is POSIX behaviour. On Windows the pipe's write **handle** is
not necessarily released by closing the C-runtime fd that wraps it, so the parent's
read never reaches EOF; `readline` keeps timing out against the profile's 0.25 s idle
budget until the 5 s absolute cap fires, and the deadline error surfaces instead of
the EOF path. The assertion under test — "a child that closes stdout and keeps
running must not leave an orphan" — is a real invariant; only its *mechanism for
producing EOF* is platform-specific.

## Evidence it is not caused by the changes it shows up under

* The test file is byte-identical to `origin/main`
  (`diff <(git show origin/main:tests/test_codex_stream_watchdog.py) tests/…` is
  empty).
* It fails with the lane's own source changes stashed away
  (`git stash push -u -- <the three changed modules>` → still `1 failed`).
* It fails alone, so it is not order-dependent on another module.

## What would fix it

Not a known-failing row — that hides a test whose invariant still matters. Either:

1. mark the EOF mechanism POSIX-only (`@pytest.mark.skipif(os.name == "nt")`) and
   keep the invariant covered on Linux, where CI runs it; or
2. give the child a Windows-correct way to release the pipe (close the underlying
   handle, or exit a wrapper process that holds it) so the same invariant is
   exercised on both hosts.

(1) is honest and small; (2) is better if the EOF path is worth proving on the host
maintainers actually develop on. Either way the fix belongs to the codex-stream
owner, not to a lane that merely ran the suite —
`docs/concerns/2026-09-25-installer-tests-dead-on-a-windows-dev-box.md` records the
same shape for the installer tests, which suggests a sweep rather than one-offs.
