"""tinyassets.outcomes — Real-world outcome tracking and evaluator adapters.

Schema (schema.py): outcome_event DDL and OutcomeEvent dataclass.
Evaluators (evaluators.py): Evaluator-protocol-conformant adapters for
  published papers (DOI), merged PRs (GitHub), deployed apps (URL liveness).
"""

from __future__ import annotations

from tinyassets.outcomes.evaluators import (
    ConferenceAcceptedEvaluator,
    DeployedAppEvaluator,
    HyperparameterImportanceEvaluator,
    MentionedInPublicationEvaluator,
    MergedPREvaluator,
    PeerReviewAcceptedEvaluator,
    PublishedPaperEvaluator,
)
from tinyassets.outcomes.schema import (
    OUTCOME_SCHEMA,
    OUTCOME_TYPES,
    OutcomeEvent,
    migrate_outcome_schema,
)

__all__ = [
    # schema.py
    "OUTCOME_SCHEMA",
    "OUTCOME_TYPES",
    "OutcomeEvent",
    "migrate_outcome_schema",
    # evaluators.py
    "ConferenceAcceptedEvaluator",
    "DeployedAppEvaluator",
    "HyperparameterImportanceEvaluator",
    "MentionedInPublicationEvaluator",
    "MergedPREvaluator",
    "PeerReviewAcceptedEvaluator",
    "PublishedPaperEvaluator",
]
