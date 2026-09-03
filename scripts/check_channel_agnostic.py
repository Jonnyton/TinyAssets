#!/usr/bin/env python3
"""No channel-specific code on the platform. A ratchet, not a wish.

Founder, 2026-09-03:

    must also be all agnostic shapes. no github spasific code should excist on
    the plateform, nor should any other spasific channel code excist. users can
    build what they need to work with any other plateform they want in what
    ever way they want to

Their universe agreed and wrote it into its brain: the platform gives users
general shape-building primitives, "not baked-in GitHub logic, not Slack logic,
not service-shaped special cases hidden in the substrate."

That is a rule you cannot hold by intention. This measures it.

    python scripts/check_channel_agnostic.py            # fail on anything new
    python scripts/check_channel_agnostic.py --report   # what is there today
    python scripts/check_channel_agnostic.py --update   # after DELETING some

The baseline records what exists now, per (file, channel). A new channel name
in the substrate fails; an increased count in a file that already has some
fails. Deleting is always allowed, and `--update` is how you record it. The
number can only go down.

Why the AST and not grep
------------------------
Most mentions of a channel in this tree are docstrings explaining why a thing is
agnostic, and counting those would make the rule unmeetable and therefore
ignored. Only string literals and identifiers that reach the runtime count.

What is deliberately not a violation
------------------------------------
`PLATFORM_OWN` names the code where the platform acts as ITSELF rather than
offering a user capability: billing its own customers through its own payment
processor, and shipping its own releases to its own forge. A user never composes
those, so no amount of channel-agnosticism in the user substrate removes them.
They are listed by name rather than skipped by pattern, so the exemption is
visible and arguable instead of silent.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
from collections import Counter

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "tinyassets"
BASELINE = REPO_ROOT / ".github" / "channel-specific-baseline.txt"

#: Names a user might want to reach. Deliberately broad: the rule is about ANY
#: channel getting special treatment, not about GitHub in particular.
CHANNELS = (
    "bitbucket", "discord", "gitea", "github", "gitlab", "gmail", "hubspot",
    "notion", "shopify", "slack", "stripe", "twilio", "twitter",
)

#: The platform acting as itself, not as a user's substrate. See the module
#: docstring: listed by name so the exemption is visible.
PLATFORM_OWN = {
    "tinyassets/billing/stripe_adapter.py",      # bills its own customers
    "tinyassets/auto_ship.py",                   # ships its own releases
    "tinyassets/auto_ship_pr.py",                # ships its own releases
    "tinyassets/workos_pipes.py",                # its own identity provider
}


def runtime_strings(path: pathlib.Path):
    """String literals and identifiers that reach the runtime.

    Docstrings are excluded: in this tree they mostly explain why something is
    agnostic, and counting them would make the rule unmeetable.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                yield node.value
        elif isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr


def survey() -> Counter:
    """``{(relative path, channel): count}`` across the user substrate."""
    counts: Counter = Counter()
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in PLATFORM_OWN:
            continue
        for text in runtime_strings(path):
            low = text.lower()
            for channel in CHANNELS:
                if channel in low:
                    counts[(rel, channel)] += 1
                    break
    return counts


def load_baseline() -> Counter:
    counts: Counter = Counter()
    if not BASELINE.is_file():
        return counts
    for raw in BASELINE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        path, channel, count = line.rsplit(":", 2)
        counts[(path, channel)] = int(count)
    return counts


def render(counts: Counter) -> str:
    lines = [
        "# Channel-specific code in the user substrate, per (file, channel).",
        "#",
        "# The founder's rule (2026-09-03): no GitHub-specific code on the",
        "# platform, and no other channel's either. This file is what exists",
        "# TODAY, so the number can only go down. Regenerate with:",
        "#     python scripts/check_channel_agnostic.py --update",
        "#",
        f"# Total: {sum(counts.values())} across {len({p for p, _ in counts})} files.",
        "",
    ]
    lines += [
        f"{path}:{channel}:{count}"
        for (path, channel), count in sorted(counts.items())
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="rewrite the baseline (use after DELETING code)")
    ap.add_argument("--report", action="store_true",
                    help="print what is there today, change nothing")
    args = ap.parse_args(argv)

    current = survey()

    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(render(current), encoding="utf-8", newline="\n")
        print(f"baseline written: {sum(current.values())} in {BASELINE}")
        return 0

    if args.report:
        for (path, channel), count in sorted(current.items(), key=lambda kv: -kv[1]):
            print(f"{count:>4}  {channel:<10} {path}")
        print(f"\ntotal {sum(current.values())} across "
              f"{len({p for p, _ in current})} files")
        return 0

    baseline = load_baseline()
    if not baseline:
        print(
            "no baseline recorded; run --update once to record what exists today",
            file=sys.stderr,
        )
        return 2

    regressions = [
        (key, count, baseline.get(key, 0))
        for key, count in sorted(current.items())
        if count > baseline.get(key, 0)
    ]
    if regressions:
        print("channel-specific code ADDED to the user substrate:", file=sys.stderr)
        for (path, channel), now, was in regressions:
            arrow = f"{was} -> {now}" if was else f"new ({now})"
            print(f"  {path}  {channel}: {arrow}", file=sys.stderr)
        print(
            "\nThe platform gives users shape-building primitives; a channel is "
            "something a USER composes, not something the substrate knows about. "
            "If this is the platform acting as itself (billing, its own releases), "
            "add the file to PLATFORM_OWN with a reason.",
            file=sys.stderr,
        )
        return 1

    removed = sum(baseline.values()) - sum(current.values())
    if removed > 0:
        print(f"channel-specific code is down {removed}; run --update to record it")
    else:
        print(f"channel-agnostic check clean ({sum(current.values())} at baseline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
