"""PR 4019 round 2: small local fixtures, pinned source, no production calls.

Run from the repository root: python docs/audits/2026-09-26-pr4019-round2-repro.py
"""
import importlib.abc
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HEAD = "508026010dab275241c5c1c807fd663333a1d156"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def source(path):
    return subprocess.check_output(["git", "show", HEAD + ":" + path], cwd=ROOT)


class Pinned(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    # Isolate review from concurrent, uncommitted changes without a checkout.
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("tinyassets.") or fullname == "scripts.migrate_private_by_default":
            relative = fullname.replace(".", "/") + ".py"
            if (ROOT / relative).is_file():
                return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        relative = module.__name__.replace(".", "/") + ".py"
        module.__file__ = str(ROOT / relative)
        exec(compile(source(relative), module.__file__, "exec"), module.__dict__)


sys.meta_path.insert(0, Pinned())
t = {}
exec(compile(source("tests/test_private_by_default.py"), "pinned-helpers", "exec"), t)

with tempfile.TemporaryDirectory(prefix="pr4019-r2-pinned-") as temporary:
    base = Path(temporary) / "output"
    base.mkdir()
    os.environ["TINYASSETS_DATA_DIR"] = str(base)
    os.environ["TINYASSETS_WIKI_PATH"] = str(Path(temporary) / "wiki")
    t["_ensure_wiki_scaffold"](Path(temporary) / "wiki")
    born, auth = t["_born"], t["_authenticate"]
    owner, stranger = t["OWNER"], t["STRANGER"]
    from scripts.migrate_private_by_default import run
    from tinyassets.api import visibility as vis
    from tinyassets.api.extensions import _extensions_impl
    from tinyassets.api.source_channel import universe_owner_actor
    from tinyassets.api.universe import _universe_impl
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
        universe_access_permission,
    )
    from tinyassets.storage import _connect
    from tinyassets.universe_server import write_graph

    born("u-owned")
    grant_universe_access(base, universe_id="u-owned", actor_id=stranger,
                          permission="write", granted_by=owner)
    auth(stranger)
    print("WRITER", write_graph(target="universe", operation="set_visibility",
                                graph_id="u-owned", visibility="public"))
    assert vis.declared_level_name("u-owned") == "private"
    born("u-content")
    secret = "retrieval.scope_mismatch SECRET_R2_CONTENT"
    (base / "u-content" / "activity.log").write_text(secret + "\n")
    for level in ["metadata_only", "public", "unlisted", "private"]:
        auth(owner)
        result = json.loads(write_graph(target="universe", operation="set_visibility",
                                         graph_id="u-content", visibility=level))
        assert result.get("status") == "updated", result
        for actor in [owner, stranger]:
            auth(actor)
            out = _extensions_impl(action="get_memory_scope_status", universe_id="u-content")
            print("MEMORY", level, actor, secret in out, json.loads(out).get("error"))
        out = _universe_impl(action="get_activity", universe_id="u-content")
        print("ACTIVITY", level, secret in out, out)
    grant_universe_access(base, universe_id="u-content", actor_id=stranger,
                          permission="read", granted_by=owner)
    out = _extensions_impl(action="get_memory_scope_status", universe_id="u-content")
    print("GRANTED_MEMORY", secret in out, json.loads(out).get("error"))
    for uid in ["u-legacy", "u-corrupt", "u-gone", "u-norules"]:
        (base / uid).mkdir()
        ensure_universe_registered(base, universe_id=uid, universe_path=base / uid)
    print(
        "ZERO_ACL",
        universe_access_permission(base, universe_id="u-legacy", actor_id=stranger),
        universe_owner_actor(base, "u-legacy", stranger),
    )
    (base / "u-gone").rmdir()
    with _connect(base) as conn:
        conn.execute(
            "UPDATE universe_rules SET metadata_json='not-json' "
            "WHERE universe_id='u-corrupt'"
        )
        conn.execute("DELETE FROM universe_rules WHERE universe_id='u-norules'")
    (base / "u-bare").mkdir()
    for uid in ["u-legacy", "u-bare"]:
        (base / uid / "activity.log").write_text(secret + "\n")
    def activity_reads():
        return [(uid, secret in _universe_impl(action="get_activity", universe_id=uid))
                for uid in ["u-legacy", "u-bare"]]
    print("MIGRATION_BEFORE", activity_reads())
    result = run(base, apply=True)
    print("MIGRATION_FLIPPED", [r["universe_id"] for r in result["flipped"]])
    print("MIGRATION_FAILED", result["failed"])
    print("MIGRATION_AFTER", activity_reads())
    second = run(base, apply=True)
    print("SECOND_APPLY_FLIPPED", second["flipped"])
    print("SECOND_APPLY_FAILED", second["failed"])
    print("OMITTED_STRANGER", write_graph(
        target="universe", operation="set_visibility", visibility="public",
    ))
    auth(owner)
    print("OMITTED_OWNER", write_graph(
        target="universe", operation="set_visibility", visibility="public",
    ))
    print("TEMP_CLEANUP", temporary)
