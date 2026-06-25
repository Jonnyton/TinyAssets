"""Import-smoke + entry-point + shared-helper consistency for the 6 canary scripts.

Defends a forever-rule uptime layer: if any canary script can't even be
imported, the corresponding CI step in `.github/workflows/uptime-canary.yml`
silently degrades to a no-op or hard-fails the runner. These tests catch
that class at PR time, before the canary goes red in production.

Coverage:
    - All 6 scripts import without side effects (parametrized).
    - Each exposes a `main` callable.
    - Log-line helpers (`_now_local_iso` / `_append_log`) are defined
      exactly once in `uptime_canary`; wiki_canary imports them.
    - HTTP+parse helpers (`_post`, `_extract_tool_text`, `_init_payload`,
      `_INITIALIZED_NOTIF`) are defined exactly once in `_canary_common`;
      mcp_tool / last_activity / revert_loop / wiki canaries import them
      (Task #14 consolidation guard — locks in the BUG-028-class fix).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


CANARY_MODULES = (
    "uptime_canary",
    "mcp_public_canary",
    "mcp_tool_canary",
    "last_activity_canary",
    "revert_loop_canary",
    "wiki_canary",
)

# Non-canary MCP-client scripts that ALSO default to the canonical public
# endpoint. Subject to the same host-directive 2026-04-20 invariant: the
# `mcp.tinyassets.io` Access-gated tunnel origin must NOT leak into any
# user-facing default. A script that drifted to `mcp.tinyassets.io` would
# silently 401/403 for any caller without CF Access service-token headers.
# Audited 2026-04-26 — these are the 4 non-canary `scripts/*.py` files
# with a `DEFAULT_URL` symbol; if a new MCP-client script is added with
# a `DEFAULT_URL` default, append it here so the same drift guard applies.
NON_CANARY_URL_SCRIPTS = (
    "navigator_wiki_sweep",
    "mcp_probe",
    "verify_llm_binding",
)


@pytest.fixture(scope="module")
def loaded_modules() -> dict[str, object]:
    """Import each canary module once. Failure here is the smoke signal."""
    return {name: importlib.import_module(name) for name in CANARY_MODULES}


@pytest.mark.parametrize("module_name", CANARY_MODULES)
def test_canary_module_importable(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.parametrize("module_name", CANARY_MODULES)
def test_canary_module_exposes_main_callable(
    module_name: str, loaded_modules: dict[str, object],
) -> None:
    mod = loaded_modules[module_name]
    assert hasattr(mod, "main"), f"{module_name} has no `main` attribute"
    assert callable(mod.main), f"{module_name}.main is not callable"


@pytest.mark.parametrize("module_name", CANARY_MODULES)
def test_canary_module_has_default_url(
    module_name: str, loaded_modules: dict[str, object],
) -> None:
    """Every canary defaults to the canonical public endpoint."""
    mod = loaded_modules[module_name]
    assert hasattr(mod, "DEFAULT_URL"), f"{module_name} has no DEFAULT_URL"
    assert mod.DEFAULT_URL == "https://tinyassets.io/mcp", (
        f"{module_name}.DEFAULT_URL drifted from the canonical "
        f"https://tinyassets.io/mcp (host directive 2026-04-20). "
        f"Got: {mod.DEFAULT_URL!r}"
    )


@pytest.mark.parametrize("module_name", NON_CANARY_URL_SCRIPTS)
def test_non_canary_script_default_url_matches_canonical(module_name: str) -> None:
    """Non-canary MCP-client scripts also lock to the canonical public endpoint.

    Same host-directive (2026-04-20) invariant as the canary scripts above:
    `mcp.tinyassets.io` is the Access-gated internal tunnel origin and must
    NOT leak into any default URL surface. A script defaulting to it would
    silently 401/403 for any caller without CF Access service-token headers.

    Sentinel against the BUG-028-class regression: a fix to one MCP-client
    script's `DEFAULT_URL` could leave the others stale. This test catches
    that drift the same way `test_canary_module_has_default_url` catches it
    on the canary side.
    """
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "DEFAULT_URL"), (
        f"{module_name} has no DEFAULT_URL — was it removed? If so, drop "
        f"it from NON_CANARY_URL_SCRIPTS in this test file."
    )
    assert mod.DEFAULT_URL == "https://tinyassets.io/mcp", (
        f"{module_name}.DEFAULT_URL drifted from the canonical "
        f"https://tinyassets.io/mcp (host directive 2026-04-20). "
        f"Got: {mod.DEFAULT_URL!r}. If `mcp.tinyassets.io` crept in, "
        f"that's the Access-gated internal tunnel origin and must not "
        f"appear in user-facing defaults."
    )


def test_log_helpers_single_definition(loaded_modules: dict[str, object]) -> None:
    """`_now_local_iso` + `_append_log` are defined in exactly one place.

    Per design: `uptime_canary` owns log-line helpers; `wiki_canary` reuses
    them by import (verified by identity check below). Other canaries don't
    persist a log line — they print to stdout/stderr and let CI/Task
    Scheduler capture the result. If a future canary adds its own copy of
    `_now_local_iso` / `_append_log`, this test fails to force the author
    to either reuse uptime_canary's helpers or justify the divergence.
    """
    uptime = loaded_modules["uptime_canary"]
    wiki = loaded_modules["wiki_canary"]

    assert hasattr(uptime, "_now_local_iso")
    assert hasattr(uptime, "_append_log")

    assert wiki._now_local_iso is uptime._now_local_iso, (
        "wiki_canary._now_local_iso must be the SAME object as "
        "uptime_canary._now_local_iso (imported, not re-defined)."
    )
    assert wiki._append_log is uptime._append_log, (
        "wiki_canary._append_log must be the SAME object as "
        "uptime_canary._append_log (imported, not re-defined)."
    )

    # Other canaries SHOULD NOT have their own copies of these names —
    # if they did, they'd be silently writing to a different log path
    # or formatting timestamps differently.
    for name in ("mcp_public_canary", "mcp_tool_canary",
                 "last_activity_canary", "revert_loop_canary"):
        mod = loaded_modules[name]
        assert not hasattr(mod, "_now_local_iso"), (
            f"{name} defines its own `_now_local_iso` — divergent from "
            f"uptime_canary. Either import from uptime_canary or document "
            f"why this canary needs a different timestamp format."
        )
        assert not hasattr(mod, "_append_log"), (
            f"{name} defines its own `_append_log` — divergent from "
            f"uptime_canary. Either import from uptime_canary or document "
            f"why this canary needs a different log path."
        )


def test_tool_canary_helpers_reused_by_wiki_canary(
    loaded_modules: dict[str, object],
) -> None:
    """`_post` / `_extract_tool_text` / `ToolCanaryError` are reused by wiki_canary.

    wiki_canary deliberately imports `_post` / `_extract_tool_text` /
    `ToolCanaryError` from `mcp_tool_canary` rather than re-implementing
    them. Verifies the chain stays connected.
    """
    tool = loaded_modules["mcp_tool_canary"]
    wiki = loaded_modules["wiki_canary"]

    assert wiki._post is tool._post
    assert wiki._extract_tool_text is tool._extract_tool_text
    # ToolCanaryError is imported by wiki_canary at module scope; verify
    # it resolves to the same class object.
    from mcp_tool_canary import ToolCanaryError as _ToolCanaryError
    assert _ToolCanaryError is tool.ToolCanaryError


# ---- Task #14 consolidation guards --------------------------------------
#
# Locks in the move of `_post`, `_extract_tool_text`, `_init_payload`, and
# `_INITIALIZED_NOTIF` to `scripts/_canary_common.py`. If a future author
# re-introduces a local copy in any of the 4 callers, these identity
# assertions fail loudly — same regression-guard pattern that
# `test_log_helpers_single_definition` provides for the log helpers.

_TOOL_CANARIES = (
    "mcp_tool_canary", "last_activity_canary",
    "revert_loop_canary", "wiki_canary",
)


@pytest.fixture(scope="module")
def common_module() -> object:
    return importlib.import_module("_canary_common")


def test_extract_tool_text_single_definition(
    loaded_modules: dict[str, object], common_module: object,
) -> None:
    """`_extract_tool_text` is the SAME function object across all 4 callers."""
    common_fn = common_module._extract_tool_text
    for name in _TOOL_CANARIES:
        mod = loaded_modules[name]
        assert mod._extract_tool_text is common_fn, (
            f"{name}._extract_tool_text drifted from "
            f"_canary_common._extract_tool_text. Re-import it from "
            f"_canary_common rather than re-defining."
        )


def test_initialized_notif_single_definition(
    loaded_modules: dict[str, object], common_module: object,
) -> None:
    """`_INITIALIZED_NOTIF` constant is the SAME object across all 4 callers."""
    common_const = common_module._INITIALIZED_NOTIF
    for name in _TOOL_CANARIES:
        mod = loaded_modules[name]
        assert mod._INITIALIZED_NOTIF is common_const, (
            f"{name}._INITIALIZED_NOTIF drifted from "
            f"_canary_common._INITIALIZED_NOTIF. Re-import it rather "
            f"than re-defining the dict literal."
        )


def test_post_underlying_function_is_common(
    loaded_modules: dict[str, object], common_module: object,
) -> None:
    """Each canary's `_post` wraps the SAME `_canary_common._post` function.

    `_post` itself is `functools.partial(_post_raw, error_factory=...,
    user_agent=...)` per canary — the partials are distinct instances but
    the underlying `partial.func` must be the canonical implementation.
    """
    common_post = common_module._post
    for name in _TOOL_CANARIES:
        mod = loaded_modules[name]
        # `wiki_canary._post` is imported from mcp_tool_canary (which IS
        # a partial); follow the .func chain to land on `_canary_common._post`.
        underlying = getattr(mod._post, "func", mod._post)
        assert underlying is common_post, (
            f"{name}._post is not backed by _canary_common._post "
            f"(got underlying={underlying!r}). Re-bind via "
            f"`functools.partial(_canary_common._post, ...)`."
        )


def test_init_payload_builder_single_definition(
    loaded_modules: dict[str, object], common_module: object,
) -> None:
    """`_init_payload` builder lives in _canary_common only.

    Each caller invokes it at module load to construct its own
    `_INIT_PAYLOAD` (with a unique `clientInfo.name`). The builder
    itself is single-source.
    """
    common_builder = common_module._init_payload
    # Spot-check via call signature: each canary's _INIT_PAYLOAD must
    # have been built by this builder. Sanity-check a known value.
    expected_names = {
        "mcp_tool_canary": "mcp-tool-canary",
        "last_activity_canary": "last-activity-canary",
        "revert_loop_canary": "revert-loop-canary",
        "wiki_canary": "wiki-canary",
    }
    for name, expected_client_name in expected_names.items():
        mod = loaded_modules[name]
        payload = mod._INIT_PAYLOAD
        assert payload == common_builder(expected_client_name), (
            f"{name}._INIT_PAYLOAD does not match the canonical builder "
            f"output for clientInfo.name={expected_client_name!r}. Drift "
            f"means a manual dict literal crept back in — replace with "
            f"`_init_payload({expected_client_name!r})`."
        )


# ---- Task #14 deferred follow-up — exception-class shape + reuse -------
#
# Per the Task #14 conservative-scope rule, exception classes were NOT
# consolidated (callers do `except XError as e` and depend on type
# identity). These tests lock in the contract that the 4 canary error
# classes:
#   1. Are `Exception` subclasses (catchable by generic `except`).
#   2. Have the consistent `(code: int, msg: str)` constructor shape used
#      by every `raise XError(step_code, "...")` site in the codebase.
#   3. Expose `code` and `msg` instance attributes (read by `main()`
#      handlers to set the exit code + format the failure line).
#   4. Are re-used by reference where appropriate (wiki_canary →
#      ToolCanaryError; uptime_canary → CanaryError) — no silent local
#      shadow class with the same name.

_CANARY_ERROR_CLASSES = {
    "mcp_public_canary": "CanaryError",
    "mcp_tool_canary": "ToolCanaryError",
    "last_activity_canary": "LastActivityError",
    "revert_loop_canary": "RevertLoopError",
}


@pytest.mark.parametrize(
    "module_name,class_name", sorted(_CANARY_ERROR_CLASSES.items()),
)
class TestCanaryExceptionShape:
    def test_class_is_exception_subclass(
        self, loaded_modules, module_name, class_name,
    ):
        mod = loaded_modules[module_name]
        cls = getattr(mod, class_name)
        assert isinstance(cls, type), (
            f"{module_name}.{class_name} is not a class: {cls!r}"
        )
        assert issubclass(cls, Exception), (
            f"{module_name}.{class_name} is not an Exception subclass"
        )

    def test_instance_has_code_and_msg_attrs(
        self, loaded_modules, module_name, class_name,
    ):
        """`(code, msg)` constructor + `.code` + `.msg` attrs locked in.

        Every raise site in the canary scripts uses this shape. main()
        handlers read `exc.code` to set the exit code and `exc.msg` to
        format the failure line. A class change that drops these attrs
        would break the canary's exit-code ladder silently.
        """
        mod = loaded_modules[module_name]
        cls = getattr(mod, class_name)
        instance = cls(42, "test message")
        assert instance.code == 42, (
            f"{module_name}.{class_name}(42, ...).code != 42 "
            f"(got {instance.code!r}); constructor signature drifted."
        )
        assert instance.msg == "test message", (
            f"{module_name}.{class_name}(..., 'test message').msg != "
            f"'test message' (got {instance.msg!r})."
        )

    def test_instance_carries_msg_in_str(
        self, loaded_modules, module_name, class_name,
    ):
        """`str(exc)` surfaces the msg so default Python error formatting
        is meaningful. Exception.__init__(msg) puts msg in args[0]."""
        mod = loaded_modules[module_name]
        cls = getattr(mod, class_name)
        instance = cls(99, "diagnostic")
        assert "diagnostic" in str(instance), (
            f"{module_name}.{class_name} does not surface msg via str(); "
            f"got {str(instance)!r}. Default Python tracebacks would "
            f"be unhelpful."
        )


def test_wiki_canary_reuses_tool_canary_error(loaded_modules):
    """wiki_canary imports ToolCanaryError from mcp_tool_canary by reference.

    All 14 raise sites in scripts/wiki_canary.py use ToolCanaryError. If
    a future edit silently re-defined a local ToolCanaryError class
    (same name, different identity), `except ToolCanaryError` blocks in
    callers would stop catching the right type. Identity check locks it.
    """
    tool = loaded_modules["mcp_tool_canary"]
    wiki = loaded_modules["wiki_canary"]
    assert wiki.ToolCanaryError is tool.ToolCanaryError, (
        "wiki_canary.ToolCanaryError is no longer the SAME class object "
        "as mcp_tool_canary.ToolCanaryError. wiki_canary must keep "
        "`from mcp_tool_canary import ToolCanaryError` rather than "
        "redefining a local class."
    )


def test_uptime_canary_reuses_public_canary_error(loaded_modules):
    """uptime_canary imports CanaryError from mcp_public_canary by reference.

    `uptime_canary.run_probe` does `except CanaryError as exc` (L121) on
    the CanaryError that `probe_result` raises. Identity drift would
    break the catch.
    """
    public = loaded_modules["mcp_public_canary"]
    uptime = loaded_modules["uptime_canary"]
    assert uptime.CanaryError is public.CanaryError, (
        "uptime_canary.CanaryError is no longer the SAME class object "
        "as mcp_public_canary.CanaryError. uptime_canary must keep "
        "`from mcp_public_canary import CanaryError` rather than "
        "redefining a local class."
    )
