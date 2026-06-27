"""Concrete dispatcher implementations for AcceptanceScenario runtime.

Each module in this package implements a dispatcher for one target_surface
per the Slice 1 design (docs/design-notes/2026-05-02-acceptance-scenario-
packs.md). Dispatchers register themselves with the scenario_runner's
registry at universe startup.

Slice 3 ships the first concrete dispatcher: `mcp_call`.
"""
