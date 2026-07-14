"""License-term composition for training inputs — fail-closed (Track G).

When a model is minted from a base model + datasets, the minted
capability's license terms must honor every input's declared terms.
This module composes declared terms mechanically and conservatively:

  * Composition is the UNION of restrictions — the result is at least
    as restrictive as every input (a lattice join).
  * ``no_derivatives`` on any input BLOCKS training outright.
  * Unknown, missing, or unrecognized licenses BLOCK. Fail-closed is
    the whole design: the expensive failure is minting a model the
    platform had no right to mint, not declining a run.
  * Share-alike inputs force the output license to carry share-alike
    (the minted model cannot be re-licensed more permissively).

IMPORTANT SCOPE NOTE: this module enforces *declared* terms
mechanically. It is not legal advice, does not interpret license
text, and cannot detect misdeclared inputs. Curation and legal review
own the registry; this module owns never being more permissive than
the registry says.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "LicenseError",
    "Terms",
    "TERMS_REGISTRY",
    "terms_for",
    "compose_terms",
    "check_trainable",
]


class LicenseError(ValueError):
    """Raised when inputs cannot legally compose — including any
    unknown license (fail-closed)."""


@dataclass(frozen=True)
class Terms:
    """Declared restrictions. False everywhere == fully permissive.
    Composition may only turn flags ON, never off."""

    license_id: str
    attribution_required: bool = False
    share_alike: bool = False  # derivatives must carry these terms
    non_commercial: bool = False
    no_derivatives: bool = False  # blocks training entirely
    named_redistribution_terms: bool = False  # e.g. Llama-style bespoke terms


# Registry of recognized declared-terms profiles. Curated; additions go
# through legal review, not code review. Anything absent → BLOCK.
TERMS_REGISTRY: dict[str, Terms] = {
    "public-domain": Terms("public-domain"),
    "cc0": Terms("cc0"),
    "mit": Terms("mit", attribution_required=True),
    "bsd-3-clause": Terms("bsd-3-clause", attribution_required=True),
    "apache-2.0": Terms("apache-2.0", attribution_required=True),
    "cc-by": Terms("cc-by", attribution_required=True),
    "cc-by-sa": Terms("cc-by-sa", attribution_required=True, share_alike=True),
    "cc-by-nc": Terms("cc-by-nc", attribution_required=True, non_commercial=True),
    "cc-by-nc-sa": Terms(
        "cc-by-nc-sa",
        attribution_required=True,
        non_commercial=True,
        share_alike=True,
    ),
    "cc-by-nd": Terms("cc-by-nd", attribution_required=True, no_derivatives=True),
    "openrail-m": Terms("openrail-m", attribution_required=True, share_alike=True),
    "llama-community": Terms(
        "llama-community",
        attribution_required=True,
        named_redistribution_terms=True,
        share_alike=True,
    ),
    "proprietary-no-training": Terms(
        "proprietary-no-training", no_derivatives=True
    ),
}


def terms_for(license_id: str) -> Terms:
    """Resolve a license id. Unknown → LicenseError (fail-closed)."""
    if not isinstance(license_id, str) or not license_id:
        raise LicenseError("license_id must be a non-empty string")
    key = license_id.strip().lower()
    terms = TERMS_REGISTRY.get(key)
    if terms is None:
        raise LicenseError(
            f"unrecognized license {license_id!r}: inputs with unregistered "
            "terms cannot be used for training (fail-closed). Register the "
            "license via curation/legal review first."
        )
    return terms


def compose_terms(inputs: list[Terms]) -> Terms:
    """Lattice join: the minted model's terms are the union of every
    input's restrictions. Raises if any input forbids derivatives or
    if the input list is empty (a training run with no declared inputs
    is a provenance failure, not a permissive default)."""
    if not inputs:
        raise LicenseError("no declared inputs: cannot compose terms")
    for t in inputs:
        if not isinstance(t, Terms):
            raise LicenseError("inputs must be Terms instances")
        if t.no_derivatives:
            raise LicenseError(
                f"input under {t.license_id!r} forbids derivatives: "
                "training is blocked"
            )
    return Terms(
        license_id="composed:" + "+".join(sorted({t.license_id for t in inputs})),
        attribution_required=any(t.attribution_required for t in inputs),
        share_alike=any(t.share_alike for t in inputs),
        non_commercial=any(t.non_commercial for t in inputs),
        no_derivatives=False,
        named_redistribution_terms=any(
            t.named_redistribution_terms for t in inputs
        ),
    )


def check_trainable(license_ids: list[str]) -> Terms:
    """Gate a training run on its declared inputs' license ids and
    return the composed terms the minted capability must carry.
    Any unknown id or no-derivatives input raises."""
    if not isinstance(license_ids, list) or not license_ids:
        raise LicenseError("license_ids must be a non-empty list")
    return compose_terms([terms_for(lic) for lic in license_ids])
