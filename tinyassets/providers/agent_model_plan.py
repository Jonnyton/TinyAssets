"""Finite advisory candidate plan; each actual attempt still needs fresh authority."""

from dataclasses import dataclass

from tinyassets.providers.model_policy import Catalog, Interaction, ModelPolicy, order_models


@dataclass(frozen=True, slots=True)
class AgentModelPlan:
    catalog: Catalog
    policy: ModelPolicy
    interaction: Interaction

    def __post_init__(self):
        if (
            type(self.catalog) is not Catalog or type(self.policy) is not ModelPolicy
            or type(self.interaction) is not Interaction or not self.interaction.needs_tools
        ):
            raise ValueError("invalid interactive candidate plan")

    def next_candidate(self, owner, universe, exhaustion=()):
        order = order_models(
            self.catalog, self.policy, self.interaction,
            owner_id=owner, universe_id=universe, exhaustion=exhaustion,
        )
        return order.candidates[0].ref if order.candidates else None
