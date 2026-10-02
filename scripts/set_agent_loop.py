"""Set one owner's agent loop on the production data root."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tinyassets.storage import data_dir
from tinyassets.storage.account_agent_loop import set_account_agent_loop


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--loop", required=True, choices=("thin", "engine"))
    parser.add_argument("--data-root", type=Path, default=None)
    args = parser.parse_args()
    print(set_account_agent_loop(
        args.data_root if args.data_root is not None else data_dir(),
        owner_user_id=args.owner, agent_loop=args.loop, updated_by="maintainer-script",
    ))


if __name__ == "__main__":
    main()
