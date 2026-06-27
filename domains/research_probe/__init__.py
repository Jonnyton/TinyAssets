"""Research Probe domain.

A minimal non-fantasy domain that demonstrates the workflow engine
is reusable without fantasy-specific state leaking in.

Exports:
    ResearchProbeDomain: The main domain class implementing
        tinyassets.protocols.Domain.
"""

from domains.research_probe.skill import ResearchProbeDomain

__all__ = ["ResearchProbeDomain"]
