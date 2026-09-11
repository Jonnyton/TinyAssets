"""Finite advisory candidate plan; each actual attempt still needs fresh authority."""

from dataclasses import dataclass

from tinyassets.providers.model_policy import (
    Catalog,
    Interaction,
    ModelPolicy,
    SourceModelPolicy,
    order_models,
)


@dataclass(frozen=True, slots=True)
class AgentModelPlan:
    catalog: Catalog
    policy: ModelPolicy
    interaction: Interaction
    policy_source: str = "unknown"
    source_policies: tuple[SourceModelPolicy, ...] = ()

    def __post_init__(self):
        if (
            type(self.catalog) is not Catalog or type(self.policy) is not ModelPolicy
            or type(self.interaction) is not Interaction or not self.interaction.needs_tools
            or type(self.policy_source) is not str
            or self.policy_source not in {"unknown", "current", "saved", "automatic"}
            or type(self.source_policies) is not tuple
            or any(type(item) is not SourceModelPolicy or not item.interaction.needs_tools
                   for item in self.source_policies)
        ):
            raise ValueError("invalid interactive candidate plan")

    def order(self, owner, universe, exhaustion=()):
        return order_models(
            self.catalog, self.policy, self.interaction,
            owner_id=owner, universe_id=universe, exhaustion=exhaustion,
            source_policies=self.source_policies,
        )

    def next_candidate(self, owner, universe, exhaustion=()):
        order = self.order(owner, universe, exhaustion)
        return order.candidates[0].ref if order.candidates else None
