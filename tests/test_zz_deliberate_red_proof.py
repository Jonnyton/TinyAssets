"""TEMPORARY — proves the `required-tests` gate can actually go red.

This file is pushed on a scratch branch only, to demonstrate that the
required check fails when a test fails, and is deleted immediately after.
A gate that has never been observed failing is not known to be a gate.
"""


def test_deliberate_failure_to_prove_the_gate_goes_red():
    assert 1 == 2, "deliberate failure — red-proof for the required-tests gate"
