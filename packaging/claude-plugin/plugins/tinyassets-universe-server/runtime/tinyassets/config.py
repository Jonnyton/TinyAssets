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

    # Engine source (how this universe's intelligence is powered) — the founder's
    # DECLARED lane. NOTE (Phase-1 scaffolding): NONE of these is a working
    # end-to-end bind-and-run lane yet. Hosted BYO-key deposit is refused through
    # the chat (a raw secret must not cross the relay); executable BYO is gated
    # behind a code-backed KMS attestation that is False until Phase 2; and
    # host_daemon / market_rented / self_hosted_endpoint have no executor routing
    # yet. A real out-of-chat deposit + real KMS + a real executor are Phase 2.
    engine_source: str = "byo_api_key"
    """How this universe DECLARES its engine lane: ``byo_api_key`` /
    ``self_hosted_endpoint`` / ``market_rented`` / ``host_daemon``. These are
    stored declarations only — none executes end-to-end in Phase-1 S5 (see the
    2026-07-02 custody note §0.2 Phase-1/Phase-2 split)."""

    engine_endpoint: str = ""
    """Self-hosted engine endpoint (e.g. an ``OLLAMA_HOST`` / ``ANTHROPIC_BASE_URL``
    URL) when ``engine_source=self_hosted_endpoint``."""

    market_model: str = ""
    """Model to rent from the market (e.g. ``glm-5.2``) when
    ``engine_source=market_rented``."""

    market_rate: float = 0.0
    """Per-unit market rate the founder accepts for a rented engine."""

    spending_cap: float = 0.0
    """Spending cap for a market-rented engine (0 = unset)."""

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


def write_universe_config_fields(
    universe_path: str | Path, **fields: Any
) -> None:
    """Merge *fields* into ``{universe_path}/config.yaml`` (atomic).

    Loads the existing config.yaml (if any), updates the given top-level keys,
    and writes the merged mapping back atomically (temp file + rename). Existing
    keys not named in *fields* are preserved. This is the write path for
    per-universe engine assignment (``preferred_writer`` /
    ``allow_api_key_providers`` set by ``universe action=set_engine``).

    Fails loudly (raises) if PyYAML is unavailable or the write fails — a
    silently-dropped engine assignment would leave the universe on the wrong
    engine (Hard Rule #8).
    """
    import os
    import tempfile

    import yaml

    config_file = Path(universe_path) / "config.yaml"
    data: dict[str, Any] = {}
    if config_file.exists():
        try:
            loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception as e:  # noqa: BLE001 - fall back to empty, log below
            logger.warning(
                "Existing config.yaml at %s unreadable (%s); rewriting fresh",
                config_file, e,
            )
    data.update(fields)

    config_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(config_file.parent), prefix=".config.", suffix=".yaml.tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=True)
        os.replace(tmp_path, config_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
