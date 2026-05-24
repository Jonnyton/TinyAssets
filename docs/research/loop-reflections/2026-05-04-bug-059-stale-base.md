# BUG-059 Stale Auto-Change PR Guard Reflection

- Surprised me: the auto-ship PR path already had a clean injected HTTP seam for POST tests, so adding a GET seam kept the stale-base guard small.
- Pattern worth capturing: PR creation from generated branches should prove branch freshness with a compare check before opening review surfaces.
- Do differently: install/check the repo dev extras earlier when the checkout starts without `pytest` or `ruff`.
