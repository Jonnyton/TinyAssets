"""A sign-in must never adopt a handle the caller chose.

The store holds RAW WorkOS refresh tokens. Two properties matter, and both were broken:

1. The `authorization_code` grant wrote the NEW user's refresh token under whatever
   `session_ref` arrived in the request body, validated for SHAPE only. Plant a handle in
   a victim's localStorage, wait for them to sign in, then renew with it: their session.
2. The files were written with `os.replace` and no chmod, so they landed at the process
   umask. Observed 0644 on production -- world-readable inside the container.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from tinyassets import onboarding


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX modes: os.chmod on Windows only toggles the read-only bit, so this "
    "asserts nothing there. Production and CI are Linux, which is where it counts.",
)
def test_a_stored_session_is_not_readable_by_anyone_else():
    handle = onboarding._mint_refresh_session("rt_secret_value")
    path = onboarding._refresh_store_dir() / f"{handle}.json"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & (stat.S_IRGRP | stat.S_IROTH) == 0, (
        f"refresh token file is group/other readable: {oct(mode)}"
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory modes")
def test_the_store_directory_is_not_traversable_by_anyone_else():
    onboarding._refresh_store_dir()
    d = onboarding._refresh_store_dir()
    mode = stat.S_IMODE(d.stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0, (
        f"refresh store directory is group/other accessible: {oct(mode)}"
    )


def test_the_token_is_written_before_the_file_is_ever_world_readable(tmp_path):
    """Not 'chmod after replace' -- the window in between is the whole problem."""
    src = (
        __import__("pathlib").Path(onboarding.__file__).read_text(encoding="utf-8")
    )
    body = src.split("def _write_refresh_session")[1].split("\ndef ")[0]
    chmod_at = body.index("chmod")
    replace_at = body.index("os.replace")
    assert chmod_at < replace_at, (
        "the mode must be narrowed BEFORE the atomic swap, or the token file exists "
        "at the umask default for a window"
    )


def test_a_new_signin_never_adopts_a_caller_supplied_handle():
    """The fixation. Reading the route source because the takeover lives in a branch,
    not in a helper -- a helper-level test would pass while the route stayed wrong."""
    src = (
        __import__("pathlib").Path(onboarding.__file__).read_text(encoding="utf-8")
    )
    assert "may_reuse_handle" in src, "the grant-aware guard is gone"
    guard = src.split("may_reuse_handle = ")[1].split("\n")[0]
    assert 'grant == "refresh_token"' in guard, (
        "a handle may only be reused by the grant that proved possession of it"
    )


def test_a_presented_handle_is_dropped_when_a_new_signin_mints_its_own():
    """Otherwise a token stays renewable under an identifier a third party may know."""
    src = (
        __import__("pathlib").Path(onboarding.__file__).read_text(encoding="utf-8")
    )
    tail = src.split("may_reuse_handle = ")[1]
    mint_branch = tail.split("else:")[1].split("elif")[0]
    assert "_drop_refresh_session(session_ref)" in mint_branch


def test_the_round_trip_still_works():
    handle = onboarding._mint_refresh_session("rt_abc")
    assert onboarding._read_refresh_session(handle) == "rt_abc"
    onboarding._drop_refresh_session(handle)
    assert onboarding._read_refresh_session(handle) == ""


def test_an_expired_session_yields_nothing_and_is_removed():
    import time

    handle = onboarding._mint_refresh_session("rt_abc")
    path = onboarding._refresh_store_dir() / f"{handle}.json"
    path.write_text(json.dumps({"rt": "rt_abc", "exp": int(time.time()) - 1}))
    assert onboarding._read_refresh_session(handle) == ""
    assert not path.exists()
