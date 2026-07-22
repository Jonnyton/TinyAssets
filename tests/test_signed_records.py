from __future__ import annotations

import copy
import pickle

import pytest

import tinyassets.runtime.signed_records as signed_records
from tinyassets.runtime.signed_records import Verified


def test_verified_cannot_be_constructed_or_subclassed() -> None:
    with pytest.raises(TypeError, match="authority verifier"):
        Verified("unverified")

    with pytest.raises(TypeError, match="cannot be subclassed"):
        class Forged(Verified[str]):
            pass


def test_verified_cannot_be_copied_or_serialized() -> None:
    proof = signed_records._verified_after_mechanism_check("checked")

    assert proof.payload == "checked"
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(proof)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(proof)
    with pytest.raises(TypeError, match="cannot be pickled"):
        pickle.dumps(proof)
