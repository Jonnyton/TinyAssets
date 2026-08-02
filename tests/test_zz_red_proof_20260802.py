"""TEMPORARY red-proof for the required-tests gate — reverted immediately.

A gate that has never been observed failing is not known to be a gate
(Codex adapt finding 7: the previous red-proof ran against the OLD direct
pytest workflow, inside an already-red run — it proved nothing about the
current quarantine aggregator). This file injects exactly ONE novel failure
into an otherwise-green run so the aggregator's green→red transition is
observed, then the commit is reverted.
"""


def test_deliberate_novel_failure_to_prove_the_aggregator_goes_red() -> None:
    raise AssertionError("red-proof: this failure must turn required-tests red")
