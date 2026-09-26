"""PR 4019 round 3: small local fixtures, pinned source, no production calls.

Run from the repository root: python docs/audits/2026-09-26-pr4019-round3-repro.py
"""
import importlib.abc
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HEAD = "4f87c39a7a9d4ae72adf40172e5f120b1f8f2b03"
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


from contextlib import contextmanager
from unittest.mock import patch

from scripts.migrate_private_by_default import run
from tinyassets.api import universe as us
from tinyassets.api import visibility as vis
from tinyassets.daemon_server import ensure_universe_registered, get_universe, get_universe_rules
from tinyassets.storage import _connect


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="pr4019-r3-") as temporary:
        base = Path(temporary) / "output"
        base.mkdir()
        os.environ["TINYASSETS_DATA_DIR"] = str(base)
        os.environ["TINYASSETS_WIKI_PATH"] = str(Path(temporary) / "wiki")
        t["_ensure_wiki_scaffold"](Path(temporary) / "wiki")
        yield base
    assert not Path(temporary).exists()

with fixture() as base:
    for name in ("u-bare", ".hidden", "lance", "output", "runs", "wiki"):
        (base / name).mkdir()
    (base / "u-bare" / "activity.log").write_text("SECRET_R3\n")
    # Plan before any daemon accessor: reproduces missing-schema precondition.
    from scripts.migrate_private_by_default import plan
    assert [r["universe_id"] for r in plan(base)["candidates"]] == ["u-bare"]
    t["_authenticate"](t["STRANGER"])
    assert "SECRET_R3" in us._universe_impl(action="get_activity", universe_id="u-bare")
    first = run(base, apply=True)
    assert first["failed"] == []
    assert [r["universe_id"] for r in first["flipped"]] == ["u-bare"]
    assert get_universe_rules(base, universe_id="u-bare")["public_read"] is False
    after = us._universe_impl(action="get_activity", universe_id="u-bare")
    assert json.loads(after)["error"] == "universe_access_denied"
    with _connect(base) as conn:
        rows = [dict(r) for r in conn.execute("SELECT universe_id, host_path FROM universes")]
    assert rows == [{"universe_id": "u-bare", "host_path": str((base / "u-bare").resolve())}]
    second = run(base, apply=True)
    assert second["flipped"] == second["failed"] == []
    print("BARE_CLOSED_RESERVED_EXCLUDED_IDEMPOTENT", rows, after)

# Differential check: the added registration must preserve existing index data.
old = {"__name__": "migration_round2"}
exec(compile(subprocess.check_output(["git", "show", "50802601:scripts/migrate_private_by_default.py"]), "round2-migration", "exec"), old)
for label, runner in [("ROUND2", old["run"]), ("ROUND3", run)]:
    with fixture() as base:
        (base / "u-existing").mkdir()
        ensure_universe_registered(base, universe_id="u-existing", universe_path=base / "u-existing",
                                   display_name="My learned name", metadata={"keep": "valuable"})
        result = runner(base, apply=True)
        assert result["failed"] == []
        record = get_universe(base, universe_id="u-existing")
        print("EXISTING_INDEX", label, record["display_name"], record["metadata"])
        if label == "ROUND2":
            assert record["display_name"] == "My learned name" and record["metadata"] == {"keep": "valuable"}
        else:
            assert record["display_name"] == "u-existing" and record["metadata"] == {}

checks = [
    ("TestMigration", "test_an_unregistered_bare_directory_is_closed_not_crashed", "registration"),
    ("TestMigration", "test_the_closed_bare_directory_stops_leaking_its_activity_log", "registration"),
    ("TestBirth", "test_birth_offers_the_same_levels_the_verb_offers", "levels"),
    ("TestBirth", "test_birth_through_the_dispatcher_refuses_it_too", "levels"),
    ("TestExposure", "test_a_real_but_unenforced_level_is_refused_as_such", "levels"),
]
for cls, name, mutation in checks:
    method = getattr(t[cls](), name)
    with fixture() as base:
        method(base)
    mutator = (patch("tinyassets.daemon_server.ensure_universe_registered", lambda *a, **k: None)
               if mutation == "registration" else patch.object(us, "_OFFERED_VISIBILITY_LEVELS", frozenset(vis.LEVELS)))
    with fixture() as base, mutator:
        try:
            method(base)
        except (AssertionError, KeyError) as exc:
            print("MUTATION_CAUGHT", name, type(exc).__name__, str(exc)[:180])
        else:
            raise AssertionError("mutation survived " + name)
print("ALL_TARGETED_CHECKS_COMPLETE; temporary fixtures removed")
