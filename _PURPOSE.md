# Purpose
Two Codex carry-overs from the fleet prune: the soul-loop test no longer leaks _FakeBranch into
tinyassets.runs (order-dependent failure), and the deploy test asserting the deleted HMAC-rotation
fleet proof step is removed (its script went with #2678).
