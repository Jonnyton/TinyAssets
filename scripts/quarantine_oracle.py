#!/usr/bin/env python3
"""Report what each quarantined test actually does on Linux.

Why this exists
---------------
`.github/known-failing-tests.txt` is written from Linux CI, but it gets drained
from developer machines — and on Windows the local result is not evidence:

- A test can SKIP locally (symlink creation needs a privilege Windows does not
  grant). A skipped test is not a passing test, and reading one as "fine" put
  two real bugs into an earlier wave of this drain.
- A test can PASS locally and still be a genuine Linux failure. The ledger is a
  Linux artifact, so a local green proves nothing about whether the entry is
  stale.

Both directions are silent. This script replaces the guess with the actual
Linux outcome, per entry, from a junit artifact that CI already uploads — so
the common case costs no new CI run at all.

Usage
-----
    # newest completed required-tests run (downloads the artifact via gh)
    python scripts/quarantine_oracle.py

    # a specific run, or an already-downloaded file
    python scripts/quarantine_oracle.py --run-id 30956724447
    python scripts/quarantine_oracle.py --junit junit.xml

    # only the entries in one file
    python scripts/quarantine_oracle.py --filter test_host_uptime_installers

Statuses
--------
    FAILED   still failing on Linux — the entry is earning its place.
             The failure message is the one to fix against.
    PASSED   passes on Linux: the entry is STALE and the gate will reject it.
    SKIPPED  skipped on Linux too — undecidable from this artifact.
    NOT RUN  never executed: excluded from this job (see
             .github/heavy-test-files.txt) or the node id no longer resolves.
             `required-tests` excludes the heavy files, so a NOT RUN here is
             usually "look at full-tests instead", not "the entry is bogus".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / ".github" / "known-failing-tests.txt"
HEAVY = REPO_ROOT / ".github" / "heavy-test-files.txt"
ARTIFACT = "junit-required-tests"


def _force_utf8_stdio() -> None:
    """Windows consoles default to cp1252 and blow up on test output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def read_ledger() -> list[str]:
    if not LEDGER.is_file():
        return []
    return [
        line.strip()
        for line in LEDGER.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def read_heavy() -> set[str]:
    if not HEAVY.is_file():
        return set()
    return {
        line.strip()
        for line in HEAVY.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def node_id(case: ET.Element) -> str | None:
    """Rebuild the pytest node id from a junit ``testcase``.

    junit does NOT store the node id. It stores ``file`` plus a ``classname``
    that is the dotted module path with the class appended when there is one,
    so the class has to be recovered by stripping the module prefix. Getting
    this wrong silently drops every class-based test from the report, which
    is most of them.
    """
    name = case.get("name") or ""
    classname = case.get("classname") or ""
    if not name:
        return None

    file = (case.get("file") or "").replace("\\", "/")
    if file:
        module_dotted = file.replace("/", ".").removesuffix(".py")
        if not classname or classname == module_dotted:
            return f"{file}::{name}"
        if classname.startswith(module_dotted + "."):
            rest = classname[len(module_dotted) + 1:]
            return f"{file}::{rest.replace('.', '::')}::{name}"
        return f"{file}::{name}"

    # `file` is only emitted by junit_family=xunit1. Under xunit2 — the modern
    # pytest default, and what a plain local run produces — the attribute is
    # absent entirely, and every entry silently reported NOT RUN until this
    # branch existed. Recover the path from the dotted classname, resolving the
    # module/class split against the filesystem rather than guessing: a dotted
    # segment can be either a subpackage or a class, and picking wrong drops
    # exactly the class-based tests, which are most of them.
    if not classname:
        return None
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = "/".join(parts[:cut]) + ".py"
        if (REPO_ROOT / candidate).is_file():
            rest = parts[cut:]
            if rest:
                return f"{candidate}::{'::'.join(rest)}::{name}"
            return f"{candidate}::{name}"
    return None


def parse_junit(path: Path) -> dict[str, tuple[str, str]]:
    """Map node id -> (status, message). Status: failed | passed | skipped."""
    root = ET.parse(path).getroot()
    out: dict[str, tuple[str, str]] = {}
    for case in root.iter("testcase"):
        nid = node_id(case)
        if nid is None:
            continue
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        skip = case.find("skipped")
        if bad is not None:
            out[nid] = ("failed", (bad.get("message") or "").strip())
        elif skip is not None:
            out[nid] = ("skipped", (skip.get("message") or "").strip())
        else:
            out[nid] = ("passed", "")
    return out


def latest_run_id(artifact: str) -> str:
    """Newest tests.yml run that actually produced the artifact."""
    raw = subprocess.run(
        ["gh", "run", "list", "--workflow=tests.yml", "--limit", "25",
         "--json", "databaseId,conclusion"],
        capture_output=True, text=True, check=True,
    ).stdout
    for row in json.loads(raw):
        if row.get("conclusion") in (None, "cancelled"):
            continue
        rid = str(row["databaseId"])
        arts = subprocess.run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/actions/runs/{rid}/artifacts",
             "--jq", ".artifacts[].name"],
            capture_output=True, text=True,
        ).stdout
        if artifact in arts:
            return rid
    raise SystemExit(
        f"no recent tests.yml run has a {artifact!r} artifact — "
        "pass --run-id or --junit explicitly"
    )


def download(run_id: str, dest: Path, artifact: str) -> Path:
    subprocess.run(
        ["gh", "run", "download", run_id, "-n", artifact, "-D", str(dest)],
        check=True, capture_output=True, text=True,
    )
    files = list(dest.glob("*.xml"))
    if not files:
        raise SystemExit(f"artifact {artifact!r} contained no .xml")
    return files[0]


def run_quarantined(ledger: list[str], dest: Path) -> Path:
    """Run the ledger's tests here and return the junit path.

    Runs whole FILES, not individual node ids, deliberately. Some ledger
    entries carry parametrized ids containing newlines, slashes and quotes
    (`...BACKUP_DEST=spaces:...\\n-symlink-600-0-partial_or_invalid`), and
    passing those through argv is a quoting hazard that fails in ways that look
    like "the test vanished". Running the file always resolves, and the report
    maps results back per entry afterwards. It also surfaces neighbours that
    broke without being quarantined.
    """
    files = sorted({n.split("::")[0] for n in ledger})
    # Written into the repo root, NOT a temp dir: the workflow uploads it as
    # an artifact after this returns, and a temp path would leave that step
    # silently finding nothing.
    junit = dest / "junit-quarantine.xml"
    cmd = [sys.executable, "-m", "pytest", *files,
           "-q", "--no-header", "-p", "no:cacheprovider",
           f"--junit-xml={junit}"]
    print(f"[oracle] running {len(files)} file(s) covering {len(ledger)} ledger entries")
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True,
                          capture_output=True, errors="replace")
    tail = (proc.stdout or "").strip().splitlines()
    if tail:
        print(f"[oracle] pytest: {tail[-1]}")
    if not junit.is_file():
        print(proc.stdout[-4000:] if proc.stdout else "(no stdout)")
        raise SystemExit("pytest produced no junit — see output above")
    return junit


def main() -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--junit", help="path to an already-downloaded junit.xml")
    ap.add_argument("--run-id", help="GitHub Actions run id to pull the artifact from")
    ap.add_argument("--artifact", default=ARTIFACT,
                    help=f"artifact to read (default {ARTIFACT}; use "
                         "junit-full-tests for the heavy files)")
    ap.add_argument("--filter", default="", help="only entries whose node id contains this")
    ap.add_argument("--quiet-failed", action="store_true",
                    help="summarize FAILED entries by count instead of listing them")
    ap.add_argument("--run", action="store_true",
                    help="run the quarantined tests HERE and report on the result, "
                         "instead of reading a CI artifact. This is what the "
                         "quarantine-oracle workflow uses on Linux.")
    ap.add_argument("--summary", help="also write the report to this file "
                                      "(point it at $GITHUB_STEP_SUMMARY in CI)")
    args = ap.parse_args()

    ledger = read_ledger()
    if not ledger:
        print("ledger is empty — nothing to report")
        return 0
    if args.filter:
        ledger = [n for n in ledger if args.filter in n]

    with tempfile.TemporaryDirectory() as tmp:
        if args.run:
            junit_path = run_quarantined(ledger, REPO_ROOT)
        elif args.junit:
            junit_path = Path(args.junit)
        else:
            rid = args.run_id or latest_run_id(args.artifact)
            print(f"[oracle] reading junit from run {rid}")
            junit_path = download(rid, Path(tmp), args.artifact)
        results = parse_junit(junit_path)

        heavy = read_heavy()
        buckets: dict[str, list[tuple[str, str]]] = {
            "failed": [], "passed": [], "skipped": [], "notrun": []}
        for nid in ledger:
            status, msg = results.get(nid, ("notrun", ""))
            buckets[status].append((nid, msg))

        out: list[str] = []
        total = len(ledger)
        out.append(f"## Quarantine oracle — {total} ledger entries vs Linux")
        out.append("")
        out.append("| status | count | meaning |")
        out.append("|---|---:|---|")
        out.append(f"| FAILED | {len(buckets['failed'])} | still failing — earning their place |")
        out.append(
            f"| PASSED | {len(buckets['passed'])} | **STALE** — the gate rejects these |"
        )
        out.append(
            f"| SKIPPED | {len(buckets['skipped'])} | skipped on Linux too — undecidable |"
        )
        out.append(f"| NOT RUN | {len(buckets['notrun'])} | not executed by this job |")

        if buckets["passed"]:
            out += ["", "### STALE — remove these from the ledger", ""]
            out += [f"- `{nid}`" for nid, _ in buckets["passed"]]

        if buckets["skipped"]:
            out += ["", "### SKIPPED on Linux — needs a different oracle", ""]
            out += [f"- `{nid}` — {msg[:100]}" for nid, msg in buckets["skipped"]]

        if buckets["notrun"]:
            out += ["", "### NOT RUN", ""]
            for nid, _ in buckets["notrun"]:
                why = ("excluded by heavy-test-files.txt — look at junit-full-tests"
                       if nid.split("::")[0] in heavy else "no matching testcase")
                out.append(f"- `{nid}` — {why}")

        if buckets["failed"] and not args.quiet_failed:
            out += ["", "### FAILED on Linux — fix against these messages", ""]
            for nid, msg in buckets["failed"]:
                first = (msg.splitlines() or [""])[0]
                out.append(f"- `{nid}`\n  - `{first[:160]}`")

        report = "\n".join(out)
        print("\n" + report)
        if args.summary:
            with open(args.summary, "a", encoding="utf-8") as fh:
                fh.write(report + "\n")

    # Reporting tool: a stale entry is information, not a failure of this run.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
