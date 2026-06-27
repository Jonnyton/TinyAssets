"""Per-universe config.yaml reader.

Each universe can have an optional ``config.yaml`` at its root with
overrides for provider preferences, temperature, timeout, and
structural limits.  Missing file or missing keys use defaults.

See AGENTS.md Input Files table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class UniverseConfig:
    """Per-universe configuration with defaults for all fields.

    Loaded from ``{universe_path}/config.yaml``.  Any field not
    specified in the YAML file uses the default value.
    """

    # Provider preferences
    preferred_writer: str = ""
    """Preferred writer provider name (e.g. 'claude-code'). Empty = use
    default fallback chain."""

    preferred_judge: str = ""
    """Preferred judge provider. Empty = use all available."""

    allowed_providers: list[str] | None = None
    """Per-universe provider allowlist (Q6.3 privacy primitive).

    None = no allowlist; the full fallback chain is preserved
    (backwards-compatible default). A list = strict allowlist; the
    router filters every fallback chain (writer/judge/extract) and the
    judge ensemble down to providers whose name appears here. If the
    filter empties a chain, the call hard-fails with
    ``AllProvidersExhaustedError`` rather than silently leaking to a
    disallowed third-party provider.

    Composes with ``TINYASSETS_PIN_WRITER``: the pin sets the chain to a
    single provider first, then the allowlist filter applies; if the
    pinned provider is not in the allowlist the call hard-fails.

    See ``docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md``
    and ``.claude/agent-memory/navigator/q63_section4_dispositions.md``
    for the design rationale."""

    # Model parameters
    temperature: float = 0.7
    """LLM temperature for creative generation."""

    timeout: int = 300
    """Subprocess / HTTP timeout in seconds."""

    max_tokens: int | None = None
    """Optional token cap for provider calls."""

    # Structural limits
    chapters_target: int = 1
    """Target number of chapters per book."""

    scenes_target: int = 3
    """Target number of scenes per chapter."""

    revision_limit: int = 1
    """Maximum second-draft revisions per scene (0 = no revisions)."""

    # Word count bounds
    min_words_per_scene: int = 200
    """Minimum word count for scene acceptance."""

    max_words_per_scene: int = 3000
    """Maximum word count for scene acceptance."""

    # Evaluation
    judge_count: int = 0
    """Number of judges for ensemble evaluation.  0 = all available."""

    debate_enabled: bool = True
    """Whether Tier 3 debate escalation is enabled."""

    # Custom overrides (catch-all for future extensions)
    extra: dict[str, Any] = field(default_factory=dict)
    """Any additional key-value pairs from config.yaml not mapped to
    a named field."""


def load_universe_config(universe_path: str | Path) -> UniverseConfig:
    """Load config.yaml from a universe directory.

    Parameters
    ----------
    universe_path : str or Path
        Root directory of the universe.

    Returns
    -------
    UniverseConfig
        Parsed config with defaults for missing fields.  Returns
        a default config if the file doesn't exist or can't be parsed.
    """
    config_file = Path(universe_path) / "config.yaml"
    if not config_file.exists():
        logger.debug("No config.yaml in %s; using defaults", universe_path)
        return UniverseConfig()

    try:
        import yaml
    except ImportError:
        logger.warning(
            "PyYAML not installed; cannot read config.yaml. "
            "Install with: pip install pyyaml"
        )
        return UniverseConfig()

    try:
        raw = config_file.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception as e:
        logger.warning("Failed to parse config.yaml: %s", e)
        return UniverseConfig()

    if not isinstance(data, dict):
        logger.warning("config.yaml is not a mapping; using defaults")
        return UniverseConfig()

    return _build_config(data)


def _build_config(data: dict[str, Any]) -> UniverseConfig:
    """Build a UniverseConfig from parsed YAML data.

    Known keys are mapped to typed fields; unknown keys go into
    ``extra``.
    """
    known_fields = {f.name for f in UniverseConfig.__dataclass_fields__.values()}
    known_fields.discard("extra")

    kwargs: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for key, value in data.items():
        if key in known_fields:
            kwargs[key] = value
        else:
            extra[key] = value

    if extra:
        kwargs["extra"] = extra

    try:
        return UniverseConfig(**kwargs)
    except (TypeError, ValueError) as e:
        logger.warning("Invalid config.yaml values: %s; using defaults", e)
        return UniverseConfig()
