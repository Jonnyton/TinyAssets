"""Guard: the platform holds no LLM credential (AGENTS.md Hard Rule 15).

Only a powered universe calls an LLM, with its owner's own connected
credentials. The daemon container, the host env file and the deploy pipeline
therefore carry NO model login, key, subscription bundle or opt-in switch. This
test is red the moment any of them reintroduces one:

* ``deploy/compose.yml`` sets no platform credential variable and mounts or
  points at no platform login directory (``/data/.codex``, ``/data/.claude``);
* ``deploy/docker-entrypoint.sh`` names the variables ONLY inside its strip
  list, strips every one of them unconditionally, and seeds or preserves no
  login;
* no GitHub workflow names one of them, keeps a host login alive, or creates
  the platform login directories;
* the host env template carries none of them, and the drop-first helper has no
  mode that logs in or exercises a host login.

``deploy/retire_platform_llm_logins.sh`` is the one file that must name them:
it deletes them from the host after a green deploy. It is checked separately to
prove it only ever deletes.

Per-universe credentials are untouched by all of this. They live inside each
universe (``<universe>/.runtime/provider-launch-credentials``, the universe's
own credential vault) and reach a provider child only through
``tinyassets.providers.base.subprocess_env_for_provider``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
COMPOSE = REPO / "deploy" / "compose.yml"
ENTRYPOINT = REPO / "deploy" / "docker-entrypoint.sh"
ENV_TEMPLATE = REPO / "deploy" / "tinyassets-env.template"
WORKFLOWS = REPO / ".github" / "workflows"
TA_OP_MODES = REPO / "deploy" / "native" / "ta_op_modes.tsv"
TA_OP_C = REPO / "deploy" / "native" / "ta_op.c"
RETIRE_SCRIPT = REPO / "deploy" / "retire_platform_llm_logins.sh"

#: Every variable through which the platform ever held, seeded, refreshed or
#: enabled a model credential. The GitHub secret names are included because a
#: workflow that reads one is exactly how a platform credential would come back.
PLATFORM_LLM_CREDENTIAL_ENV: frozenset[str] = frozenset({
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "TINYASSETS_ALLOW_API_KEY_PROVIDERS",
    "TINYASSETS_CODEX_AUTH_JSON_B64",
    "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
    "WORKFLOW_CODEX_AUTH_JSON_B64",
    "WORKFLOW_CLAUDE_CREDENTIALS_JSON_B64",
})

#: Where the platform kept its own CLI logins on the data volume.
PLATFORM_LOGIN_DIRS: tuple[str, ...] = ("/data/.codex", "/data/.claude")

#: Drop-first helper modes that exercised or created a host login.
PLATFORM_LOGIN_MODES: frozenset[str] = frozenset({
    "codex-keepalive",
    "claude-keepalive",
    "claude-login",
})

_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(sorted(PLATFORM_LLM_CREDENTIAL_ENV)) + r")(?![A-Za-z0-9_])"
)


def _names_in(text: str) -> set[str]:
    return set(_NAME_RE.findall(text))


def _strip_array(text: str) -> tuple[str, set[str]]:
    """Return (entrypoint text outside the strip array, names inside it)."""
    match = re.search(
        r"^_platform_credential_env=\(\n(?P<body>.*?)^\)\n",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, (
        "docker-entrypoint.sh must declare its strip list as a "
        "`_platform_credential_env=( ... )` array"
    )
    inside = {
        line.strip()
        for line in match.group("body").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    outside = text[: match.start()] + text[match.end():]
    return outside, inside


# ---------------------------------------------------------------------------
# compose
# ---------------------------------------------------------------------------


def test_compose_sets_no_platform_llm_credential():
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    offenders: dict[str, list[str]] = {}
    for name, service in (compose.get("services") or {}).items():
        env = service.get("environment") or {}
        keys = (
            list(env)
            if isinstance(env, dict)
            else [str(item).split("=", 1)[0] for item in env]
        )
        bad = sorted(set(keys) & PLATFORM_LLM_CREDENTIAL_ENV)
        if bad:
            offenders[name] = bad
    assert not offenders, f"compose services set platform LLM credentials: {offenders}"


def test_compose_text_names_no_platform_credential_or_login_dir():
    text = COMPOSE.read_text(encoding="utf-8")
    assert not _names_in(text), sorted(_names_in(text))
    for path in PLATFORM_LOGIN_DIRS:
        assert path not in text, f"compose still references {path}"


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def test_entrypoint_names_credentials_only_to_strip_them():
    outside, inside = _strip_array(ENTRYPOINT.read_text(encoding="utf-8"))
    leaked = _names_in(outside)
    assert not leaked, (
        "docker-entrypoint.sh names a platform LLM credential outside its strip "
        f"list: {sorted(leaked)}"
    )
    missing = PLATFORM_LLM_CREDENTIAL_ENV - inside
    assert not missing, f"entrypoint strip list misses {sorted(missing)}"


def test_entrypoint_strips_unconditionally_and_seeds_no_login():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    outside, _ = _strip_array(text)
    # The strip loop runs for every name with no opt-in branch around it.
    assert re.search(
        r'^for _name in "\$\{_platform_credential_env\[@\]\}"; do$',
        outside,
        flags=re.MULTILINE,
    ), "the strip loop must be top-level (unconditional)"
    assert re.search(r'^\s+unset "\$\{_name\}"$', outside, flags=re.MULTILINE)
    for path in PLATFORM_LOGIN_DIRS:
        assert path not in text, f"entrypoint still references {path}"
    for needle in ("auth.json", ".credentials.json", "base64 -d"):
        assert needle not in outside, f"entrypoint still handles a login: {needle!r}"


# ---------------------------------------------------------------------------
# workflows
# ---------------------------------------------------------------------------


def _workflow_files() -> list[Path]:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert files, "no workflows found"
    return files


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_no_workflow_holds_or_refreshes_a_platform_llm_credential(workflow: Path):
    text = workflow.read_text(encoding="utf-8")
    assert not _names_in(text), (
        f"{workflow.name} names platform LLM credentials: {sorted(_names_in(text))}"
    )
    for path in PLATFORM_LOGIN_DIRS:
        assert path not in text, f"{workflow.name} references {path}"
    for mode in PLATFORM_LOGIN_MODES:
        assert f"ta-op {mode}" not in text, f"{workflow.name} runs ta-op {mode}"
    assert not re.search(r"\$VOLUME_DIR/\.(codex|claude)\b", text), (
        f"{workflow.name} creates a platform login directory on the data volume"
    )


def test_keepalive_workflows_are_gone():
    for name in ("codex-auth-keepalive.yml", "claude-auth-keepalive.yml"):
        assert not (WORKFLOWS / name).exists(), f"{name} keeps a host login alive"


def test_deploy_runs_the_retirement_only_after_a_green_canary():
    deploy = yaml.safe_load((WORKFLOWS / "deploy-prod.yml").read_text(encoding="utf-8"))
    steps = deploy["jobs"]["deploy"]["steps"]
    names = [step.get("name", "") for step in steps]
    retire_idx = next(
        (
            i for i, s in enumerate(steps)
            if "retire_platform_llm_logins.sh" in str(s.get("run", ""))
        ),
        None,
    )
    assert retire_idx is not None, "deploy must run deploy/retire_platform_llm_logins.sh"
    canary_idx = next(i for i, s in enumerate(steps) if s.get("id") == "canary")
    assert retire_idx > canary_idx, (
        "the host cleanup must run after the public canary, never before: "
        f"{names[retire_idx]!r} precedes the canary"
    )
    condition = str(steps[retire_idx].get("if", ""))
    assert "steps.canary.outcome == 'success'" in condition, condition


# ---------------------------------------------------------------------------
# env template + drop-first helper
# ---------------------------------------------------------------------------


def test_env_template_carries_no_platform_llm_credential():
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert not _names_in(text), sorted(_names_in(text))
    for path in PLATFORM_LOGIN_DIRS:
        assert path not in text


def test_ta_op_has_no_host_login_mode():
    modes = {
        line.split("\t", 1)[0]
        for line in TA_OP_MODES.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert not modes & PLATFORM_LOGIN_MODES, sorted(modes & PLATFORM_LOGIN_MODES)
    source = TA_OP_C.read_text(encoding="utf-8")
    for mode in PLATFORM_LOGIN_MODES:
        assert f'"{mode}"' not in source, f"ta_op.c still implements {mode}"


# ---------------------------------------------------------------------------
# the retirement script only ever deletes
# ---------------------------------------------------------------------------


def test_retire_script_only_deletes():
    text = RETIRE_SCRIPT.read_text(encoding="utf-8")
    # It never writes a value into the env file.
    assert not re.search(r"install-tinyassets-env\.sh\"?\s+set", text)
    assert "set-once" not in text
    # It removes exactly the retired names, no fewer.
    runtime_names = PLATFORM_LLM_CREDENTIAL_ENV - {
        "WORKFLOW_CODEX_AUTH_JSON_B64",
        "WORKFLOW_CLAUDE_CREDENTIALS_JSON_B64",
    }
    missing = runtime_names - _names_in(text)
    assert not missing, f"retire script does not scrub {sorted(missing)}"
