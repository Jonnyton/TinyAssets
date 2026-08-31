# Node code reaches `subprocess` and `os` through `ws.read.__func__.__globals__`

**Found** 2026-08-31, on `origin/main` (`acc0b11a`), in the Linux oracle
container (bwrap 0.12.0). **Severity P1** — it defeats every *software* guard
the code node advertises, but the bubblewrap jail still contains it.

Surfaced by a Codex refute review of PR #2738 (claim Q5), then reproduced
against `main` rather than against the PR branch, because the first question
was whether the PR introduced it. It did not.

## What actually happens

Node code is untrusted, user-authored Python. Two software guards are supposed
to bound it: `FORBIDDEN_PATTERNS` (a source denylist) and `ALLOWED_IMPORTS`
(an import allowlist that replaces `__import__`). The `ws` object is injected
into the node's namespace so it can reach its workspace.

`ws` is an instance of `_Workspace`, defined in the runner script's module
namespace. Python hands every function its defining module's globals, so:

```python
def run(state):
    g = ws.read.__func__.__globals__          # the runner module's globals
    sp = g['sub' + 'process']                  # denylist matches a literal only
    p = sp.run(['/usr/local/bin/python', '-c', 'print(7*6)'],
               capture_output=True, text=True)
    return {'result': {'rc': p.returncode, 'stdout': p.stdout.strip()}}
```

Measured in the real jail: **`rc=0`, `stdout='42'`.** The node passed
validation and spawned a process.

`__globals__` exposes **66 names**, including `subprocess`, `os`,
`_original_import` (the *unrestricted* `__import__` the allowlist replaced),
`_restricted_import`, `_get_frame` and `_ws_kill_group`. `_original_import`
alone reduces `ALLOWED_IMPORTS` to decoration: anything the interpreter can
import is reachable.

The denylist does not help. It matches source literals, so `'sub' + 'process'`
passes; `globals(` is on the list but `__globals__` is not, and adding it would
be another literal to concatenate around.

## What this does NOT reach

Checked before assigning severity, because it decides whether this is P0:

* **No credentials.** The code-node jail binds no broker socket, no
  `GIT_ASKPASS`, no credential mount. Git runs in the *effector*, not here.
* **No `/data`, no universe root.** `_bwrap_argv` binds `/usr`, `/bin`,
  `/lib`, `/lib64` read-only, `--dev /dev`, `--proc /proc`, `--tmpfs /tmp`,
  plus at most the one `/workspace` bind.
* **No network.** `--unshare-all` with no `--share-net`.

So the blast radius is the node's own workspace, a private tmpfs, and CPU and
memory spent outside `ws.run`'s accounting. It is a broken guarantee and a
budget bypass, not a host compromise or a credential leak.

## Why no test caught it

The six hostile-code jail tests in `tests/test_node_sandbox.py` — including
`test_jail_runs_a_node_at_all`, the positive control — **skip everywhere**.
They gate on `providers.base.probe_sandbox_available`, which carried a second,
divergent bwrap probe (`--ro-bind / / /bin/sh -c true`). Measured side by side
in the oracle: that probe exits 1 while the launcher's real argv exits 0. So on
CI and in the oracle the tests skipped rather than ran, and a skip reads as a
pass in a summary line. See [[a-skipped-test-rots-silently]].

The probe divergence is fixed in the same change as this file. That fix is what
makes any test written for this concern able to run at all — write the fix for
this concern **after** confirming those six tests now execute.

## The shape of a fix (not yet decided)

Making `__globals__` unreachable by denylisting it is the wrong shape — it is
one more literal to evade. The object handed across the boundary should not
carry a reference to the runner's module namespace at all:

* build `_Workspace` by `exec`-ing its definition in a **minimal namespace**
  holding only what it needs, so `__globals__` is inert; and/or
* drop `subprocess`, `os` and `_original_import` from the runner's module
  globals once the closures that need them are built.

## The audit, done — and it rules out the obvious fix

`ws` is **not** the only door. Exactly two names are injected
(`node_sandbox.py:1261-1263`): `invoke_mcp_action` and `ws`. Measured in the
jail on the Linux oracle:

```
run.__globals__                 ->  4 names, subprocess: False
invoke_mcp_action.__globals__   -> 68 names, subprocess: True, _original_import: True
                                   is ws.read.__func__.__globals__: True
```

Three things follow, and the third is the one that matters:

1. The node's OWN namespace is clean — `run.__globals__` holds 4 names and no
   modules. `exec(source_code, namespace)` is doing its job.
2. `invoke_mcp_action` is an equally good door, and it is a plain function, so
   it has no `__func__` indirection to remove.
3. **Both doors are the SAME dict.** So any fix aimed at `ws` alone — a proxy
   object, a `__getattr__` wrapper, hiding `__func__` — achieves nothing,
   because `invoke_mcp_action.__globals__` still reaches the identical
   namespace. The leak is the shared runner module, not either object.

That kills the "wrap `ws`" family of fixes. What is left:

* **Shrink the runner namespace itself** — `del` the module references once the
  closures that need them are built, so there is nothing worth reaching. Needs
  care: `_original_import` is used by `_restricted_import`, so it has to become
  a closure cell or a default argument rather than a module global.
* **Build both injected callables in a minimal namespace** — `exec` their
  definitions in a dict holding only what they need, so `__globals__` is inert
  for both. Costs a restructure of the runner script.

The first is smaller and probably sufficient; the second is the one that stays
correct when a third injected name is added.

A fix is not proven until it is asserted by a test that runs *inside* bwrap on
the Linux oracle, and that goes red on the tree above.
