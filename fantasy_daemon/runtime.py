"""Shim: ``fantasy_daemon.runtime`` IS ``tinyassets.runtime_singletons``.

Re-binding ``sys.modules`` so ``import fantasy_daemon.runtime`` returns
the same module object as ``import tinyassets.runtime_singletons``. A bare
``from tinyassets.runtime_singletons import *`` would only snapshot bindings at
import time, so writes via one alias would not be visible through the
other — that mismatch silently broke daemon/API state sharing.
"""
import sys

import tinyassets.runtime_singletons as _wr

sys.modules[__name__] = _wr
