"""The resolver's staging and command layer, and the locked fixture it runs on.

Two properties carry the weight here and both are asserted directly rather than
through a shape check. The digest one: what the installer reads must be what
admission validated, so staging reads the bytes back off disk and hashes those.
The argv one: a path that begins with a dash is an option, not a path, so it is
refused before it can reach ``pip`` or ``npm``.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess

import pytest

from tinyassets import workspace_resolver as wr
from tinyassets.workspace_provision import admit_node, admit_requirements
from tinyassets.workspace_resolver import (
    ResolverError,
    npm_fetch_argv,
    npm_offline_install_argv,
    pip_download_argv,
    pip_offline_install_argv,
    resolver_environment,
    stage_node_plan,
    stage_python_plan,
)

FIXTURE = (
    pathlib.Path(__file__).parent / "fixtures" / "workspace" / "requirements-locked.txt"
)
SRI_512 = "sha512-" + "A" * 86 + "=="


# ──────────────────────────────────────────────────────────────────────────────
# The locked fixture
# ──────────────────────────────────────────────────────────────────────────────


def test_the_locked_fixture_is_admitted() -> None:
    """Generated with real `pip download` + `pip hash`, not shaped to pass."""
    plan = admit_requirements(FIXTURE.read_text(encoding="utf-8"))
    assert {record.name for record in plan.records} == {
        "pytest", "pluggy", "iniconfig", "packaging", "pygments", "colorama",
    }


def test_every_locked_record_is_pinned_and_hashed() -> None:
    plan = admit_requirements(FIXTURE.read_text(encoding="utf-8"))
    for record in plan.records:
        assert record.hashes, record.name
        for digest in record.hashes:
            assert digest.startswith("sha256:")
            assert len(digest) == len("sha256:") + 64
        # `==` is not observable on the record (there is no operator field
        # because there is no other operator); the canonical line is where it
        # shows, and admission would have refused anything else.
        assert f"{record.name}=={record.version}" in record.canonical()


def test_the_windows_only_dependency_keeps_its_marker() -> None:
    """Dropping it would leave the closure short on Windows; carrying it without
    the marker would install it on Linux."""
    plan = admit_requirements(FIXTURE.read_text(encoding="utf-8"))
    colorama = next(r for r in plan.records if r.name == "colorama")
    assert colorama.marker == 'sys_platform == "win32"'
    others = [r for r in plan.records if r.name != "colorama"]
    assert all(record.marker is None for record in others)


def test_the_fixture_round_trips_through_admission() -> None:
    plan = admit_requirements(FIXTURE.read_text(encoding="utf-8"))
    again = admit_requirements(plan.normalized_text)
    assert again.digest == plan.digest


def test_real_node_fixture_round_trips_and_keeps_its_registry_integrity(tmp_path):
    fixture = FIXTURE.parent / "node"
    plan = admit_node((fixture / "package.json").read_text(encoding="utf-8"),
                      (fixture / "package-lock.json").read_text(encoding="utf-8"))
    staged = stage_node_plan(plan, tmp_path)
    again = admit_node(staged.package_json.read_text(encoding="utf-8"),
                       staged.lockfile.read_text(encoding="utf-8"))
    assert again.digest == plan.digest
    package = json.loads(again.normalized_lockfile)["packages"]["node_modules/picocolors"]
    assert package["version"] == "1.1.1"
    assert package["resolved"] == "https://registry.npmjs.org/picocolors/-/picocolors-1.1.1.tgz"
    assert package["integrity"] == (
        "sha512-xceH2snhtb5M9liqDsmEw56le376mTZkEX/jEb/RxNFyegNul7eNslCXP9FDj/"
        "Lcu0X8KEyMceP2ntpaHrDEVA==")


# ──────────────────────────────────────────────────────────────────────────────
# Staging
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def python_plan():
    return admit_requirements(FIXTURE.read_text(encoding="utf-8"))


def _manifest_text() -> str:
    return json.dumps(
        {"name": "app", "version": "1.0.0", "dependencies": {"left-pad": "^1.3.0"}}
    )


def _lockfile_text() -> str:
    return json.dumps(
        {
            "name": "app",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "packages": {
                "": {
                    "name": "app",
                    "version": "1.0.0",
                    "dependencies": {"left-pad": "^1.3.0"},
                },
                "node_modules/left-pad": {
                    "version": "1.3.0",
                    "resolved": (
                        "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz"
                    ),
                    "integrity": SRI_512,
                },
            },
        }
    )


@pytest.fixture()
def node_plan():
    return admit_node(_manifest_text(), _lockfile_text())


def test_staging_writes_the_admitted_text_and_binds_it(python_plan, tmp_path) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    assert staged.path.name == "requirements.canonical.txt"
    assert staged.path.parent == pathlib.Path(str(tmp_path.resolve()))
    on_disk = staged.path.read_bytes()
    assert on_disk == python_plan.normalized_text.encode("utf-8")
    assert staged.digest == hashlib.sha256(on_disk).hexdigest()
    assert staged.digest == python_plan.digest


def test_the_staged_text_is_itself_admissible(python_plan, tmp_path) -> None:
    """The file the installer reads must be a file admission would admit."""
    staged = stage_python_plan(python_plan, tmp_path)
    again = admit_requirements(staged.path.read_text(encoding="utf-8"))
    assert again.digest == python_plan.digest


def test_a_digest_that_does_not_match_the_plan_refuses(python_plan, tmp_path) -> None:
    """The whole point of staging: bytes that are not what was admitted stop here."""
    from dataclasses import replace

    lying = replace(python_plan, digest="0" * 64)
    with pytest.raises(ResolverError, match="does not match the admitted plan"):
        stage_python_plan(lying, tmp_path)


def test_a_write_that_lies_about_what_landed_is_caught(
    python_plan, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hashing what we MEANT to write would pass here; hashing what is on disk
    is what makes the digest a statement about the file the installer opens.
    """
    real_write = wr.os.write

    def lying_write(handle: int, data: bytes) -> int:
        real_write(handle, data[: len(data) // 2])
        return len(data)

    monkeypatch.setattr(wr.os, "write", lying_write)
    with pytest.raises(ResolverError, match="does not match the admitted plan"):
        stage_python_plan(python_plan, tmp_path)


def test_staging_twice_refuses_rather_than_overwriting(python_plan, tmp_path) -> None:
    stage_python_plan(python_plan, tmp_path)
    with pytest.raises(ResolverError, match="already exists"):
        stage_python_plan(python_plan, tmp_path)


def test_a_staging_directory_must_exist_and_be_absolute(python_plan, tmp_path) -> None:
    with pytest.raises(ResolverError, match="does not exist"):
        stage_python_plan(python_plan, tmp_path / "absent")
    with pytest.raises(ResolverError, match="must be absolute"):
        stage_python_plan(python_plan, pathlib.Path("relative"))


def test_node_staging_writes_both_and_binds_the_pair(node_plan, tmp_path) -> None:
    staged = stage_node_plan(node_plan, tmp_path)
    assert staged.package_json.name == "package.json"
    assert staged.lockfile.name == "package-lock.json"
    manifest_bytes = staged.package_json.read_bytes()
    lockfile_bytes = staged.lockfile.read_bytes()
    assert manifest_bytes == node_plan.normalized_package_json.encode("utf-8")
    assert lockfile_bytes == node_plan.normalized_lockfile.encode("utf-8")
    assert staged.digest == hashlib.sha256(
        manifest_bytes + b"\x00" + lockfile_bytes
    ).hexdigest()
    assert staged.digest == node_plan.digest


def test_a_node_digest_that_does_not_match_refuses(node_plan, tmp_path) -> None:
    from dataclasses import replace

    lying = replace(node_plan, digest="0" * 64)
    with pytest.raises(ResolverError, match="does not match the admitted plan"):
        stage_node_plan(lying, tmp_path)


# ──────────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────────


def test_the_download_argv_is_exactly_this(python_plan, tmp_path) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    cache = tmp_path / "cache"
    assert pip_download_argv(staged, cache, python="python3") == [
        "python3",
        "-I", "-m", "pip", "download",
        "--isolated",
        "--disable-pip-version-check",
        "--no-input",
        "--only-binary=:all:",
        "--require-hashes",
        "--proxy", "http://127.0.0.1:3128",
        "--index-url", "https://pypi.org/simple",
        "--dest", str(cache),
        "-r", str(staged.path),
    ]


def test_the_download_argv_carries_no_no_deps(python_plan, tmp_path) -> None:
    """pip needs a hash for every file it downloads, so the plan must pin the
    whole closure; ``--no-deps`` would hide an incomplete one instead."""
    staged = stage_python_plan(python_plan, tmp_path)
    assert "--no-deps" not in pip_download_argv(
        staged, tmp_path / "cache", python="python3"
    )


def test_the_offline_install_argv_is_exactly_this(python_plan, tmp_path) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    cache = tmp_path / "cache"
    venv = tmp_path / "venv" / "bin" / "python"
    assert pip_offline_install_argv(staged, cache, venv) == [
        str(venv),
        "-I", "-m", "pip", "install",
        "--isolated",
        "--disable-pip-version-check",
        "--no-input",
        "--no-index",
        "--find-links", str(cache),
        "--require-hashes",
        "--only-binary=:all:",
        "-r", str(staged.path),
    ]


def test_the_offline_install_reaches_no_index(python_plan, tmp_path) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    argv = pip_offline_install_argv(staged, tmp_path / "cache", tmp_path / "python")
    assert "--no-index" in argv
    assert "--index-url" not in argv
    assert not [item for item in argv if item.startswith("http")]


@pytest.mark.parametrize("command", ["download", "install"])
def test_pip_really_accepts_builder_options(
    python_plan, tmp_path, monkeypatch, command
) -> None:
    """Parse the real command, without installing, fetching or host config."""
    from pip._internal.commands import create_command

    monkeypatch.setenv("PIP_CONFIG_FILE", os.devnull)
    staged = stage_python_plan(python_plan, tmp_path)
    argv = (
        pip_download_argv(staged, tmp_path / "cache", python="python3")
        if command == "download"
        else pip_offline_install_argv(staged, tmp_path / "cache", tmp_path / "python")
    )
    options, args = create_command(command, isolated=True).parse_args(argv[5:])
    assert args == []
    assert options.isolated_mode is True
    assert options.no_input is True
    assert options.disable_pip_version_check is True
    assert options.require_hashes is True
    assert options.requirements == [str(staged.path)]
    assert options.format_control.only_binary == {":all:"}
    if command == "download":
        assert options.proxy == "http://127.0.0.1:3128"
        assert options.index_url == wr.DEFAULT_INDEX_URL
        assert options.download_dir == str(tmp_path / "cache")
    else:
        assert not options.proxy
        assert options.no_index is True
        assert options.find_links == [str(tmp_path / "cache")]


@pytest.mark.parametrize("command", ["download", "install"])
def test_pip_rejects_the_old_no_config_option(monkeypatch, capsys, command) -> None:
    from pip._internal.commands import create_command

    monkeypatch.setenv("PIP_CONFIG_FILE", os.devnull)
    with pytest.raises(SystemExit) as error:
        create_command(command, isolated=True).parse_args(["--isolated", "--no-config"])
    assert error.value.code == 2
    assert "no such option: --no-config" in capsys.readouterr().err


def test_the_npm_fetch_argv_is_exactly_this(node_plan, tmp_path) -> None:
    staged = stage_node_plan(node_plan, tmp_path)
    cache = tmp_path / "cache"
    assert npm_fetch_argv(staged, cache) == [
        "npm", "ci",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--cache", str(cache),
        "--userconfig", wr.NULL_DEVICE,
        "--registry", "https://registry.npmjs.org",
        "--prefix", str(staged.directory),
        "--proxy", "http://127.0.0.1:3128",
        "--https-proxy", "http://127.0.0.1:3128",
        "--noproxy=",
    ]


def test_npm_offline_is_proxy_free_and_permits_dependency_scripts(node_plan, tmp_path) -> None:
    staged = stage_node_plan(node_plan, tmp_path)
    offline = npm_offline_install_argv(staged, tmp_path / "cache")
    assert "--offline" in offline
    assert "--ignore-scripts" not in offline
    assert "--proxy" not in offline
    assert "--https-proxy" not in offline
    assert not any("127.0.0.1" in token for token in offline)
    # The caller stages this canonical root before install, never the original
    # checkout manifest. Dependency scripts run offline; root hooks do not.
    assert "scripts" not in json.loads(staged.package_json.read_text())


def test_npm_never_runs_a_lifecycle_script_while_fetching(node_plan, tmp_path) -> None:
    staged = stage_node_plan(node_plan, tmp_path)
    assert "--ignore-scripts" in npm_fetch_argv(staged, tmp_path / "cache")


@pytest.mark.parametrize("offline", [False, True])
def test_real_npm_parses_acquisition_and_offline_options(node_plan, tmp_path, offline):
    """Ask the installed npm parser, without fetching or installing any package."""
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        pytest.skip("real npm parser requires installed Node/npm")
    command = pathlib.Path(npm).resolve()
    cli = (command if command.name == "npm-cli.js" else
           command.parent / "node_modules" / "npm" / "bin" / "npm-cli.js")
    if not cli.is_file():
        pytest.skip("installed npm entry point could not be resolved")
    staged = stage_node_plan(node_plan, tmp_path)
    builder = npm_offline_install_argv if offline else npm_fetch_argv
    argv = builder(staged, tmp_path / "cache")
    env = resolver_environment(tmp_path, str(pathlib.Path(node).parent))
    if os.name == "nt":
        env["SystemRoot"] = os.environ["SystemRoot"]
        env["USERPROFILE"] = str(tmp_path)
    # Replace only the subcommand. The actual emitted options remain intact.
    # Suppress the test machine's global npmrc as well as the builder's usercfg.
    # npm on Linux refuses the same filename in two config layers: userconfig
    # is already /dev/null. A distinct empty fixture isolates global config
    # without changing any of the builder's options under test.
    global_config = tmp_path / "empty-global.npmrc"
    global_config.write_text("", encoding="utf-8")
    result = subprocess.run(
        [node, str(cli), "config", "list", "--json", "--globalconfig",
         str(global_config), *argv[2:]],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["offline"] is offline
    assert config["ignore-scripts"] is not offline
    if offline:
        assert config["proxy"] is None
        assert config["https-proxy"] is None
    else:
        # npm's URL config type may serialize the origin with a trailing slash.
        assert config["proxy"] in {wr.REGISTRY_PROXY_URL, wr.REGISTRY_PROXY_URL + "/"}
        assert config["https-proxy"] in {wr.REGISTRY_PROXY_URL, wr.REGISTRY_PROXY_URL + "/"}
        assert config["noproxy"] in ("", [""])


def test_the_argv_gate_refuses_a_dash_token_no_builder_chose() -> None:
    """``_admitted_argv`` is the module's last look at its own output.

    Every caller-supplied path is already refused by the path checks, so no
    input reaches this gate today -- which is exactly why it is driven directly.
    It exists for the next builder, or a typo in one, and a gate that cannot be
    shown to fire is decoration.
    """
    from tinyassets.workspace_resolver import _admitted_argv

    with pytest.raises(ResolverError, match="begins with a dash"):
        _admitted_argv(["python3", "-m", "pip", "--trusted-host", "evil.example"])
    with pytest.raises(ResolverError, match="begins with a dash"):
        _admitted_argv(["python3", "--extra-index-url", "https://evil.example"])
    with pytest.raises(ResolverError, match="empty element"):
        _admitted_argv(["python3", ""])
    with pytest.raises(ResolverError, match="NUL"):
        _admitted_argv(["python3", "pi" + chr(0) + "p"])

    admitted = ["python3", "-m", "pip", "download", "--isolated"]
    assert _admitted_argv(list(admitted)) == admitted


def test_every_dash_token_the_builders_emit_is_declared(
    python_plan, node_plan, tmp_path
) -> None:
    """FIXED_FLAGS is the allowlist; drift between it and the builders would
    either refuse a real command or widen the gate silently."""
    staged = stage_python_plan(python_plan, tmp_path)
    node_dir = tmp_path / "node"
    node_dir.mkdir()
    staged_node = stage_node_plan(node_plan, node_dir)
    emitted: set[str] = set()
    for argv in (
        pip_download_argv(staged, tmp_path / "cache", python="python3"),
        pip_offline_install_argv(staged, tmp_path / "cache", tmp_path / "python"),
        npm_fetch_argv(staged_node, tmp_path / "cache"),
        npm_offline_install_argv(staged_node, tmp_path / "cache"),
    ):
        emitted.update(item for item in argv if item.startswith("-"))
    assert emitted <= wr.FIXED_FLAGS
    unused = wr.FIXED_FLAGS - emitted
    assert not unused, f"FIXED_FLAGS declares tokens no builder emits: {unused}"


DASH_LEADING = ["-rf", "--index-url", "--prefix=/etc", "-"]


@pytest.mark.parametrize("hostile", DASH_LEADING)
def test_a_cache_directory_that_would_be_read_as_an_option_refuses(
    python_plan, tmp_path, hostile: str
) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    with pytest.raises(ResolverError, match="begins with a dash"):
        pip_download_argv(staged, hostile, python="python3")


@pytest.mark.parametrize("hostile", DASH_LEADING)
def test_an_executable_that_would_be_read_as_an_option_refuses(
    python_plan, tmp_path, hostile: str
) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    with pytest.raises(ResolverError, match="begins with a dash"):
        pip_download_argv(staged, tmp_path / "cache", python=hostile)


@pytest.mark.parametrize("hostile", DASH_LEADING)
def test_a_dash_leading_npm_cache_refuses(node_plan, tmp_path, hostile: str) -> None:
    staged = stage_node_plan(node_plan, tmp_path)
    with pytest.raises(ResolverError, match="begins with a dash"):
        npm_fetch_argv(staged, hostile)


def test_a_dash_leading_staged_path_refuses(python_plan, tmp_path) -> None:
    """Belt and braces: staging names the file, but the builder re-checks it."""
    from tinyassets.workspace_resolver import StagedManifest

    lying = StagedManifest(path=pathlib.Path("--index-url"), digest="0" * 64)
    with pytest.raises(ResolverError, match="begins with a dash"):
        pip_download_argv(lying, tmp_path / "cache", python="python3")


BAD_PATHS = [
    ("relative", "cache"),
    ("nul", "/tmp/ca\x00che"),
    ("empty", ""),
]


@pytest.mark.parametrize(
    ("value"), [pytest.param(value, id=name) for name, value in BAD_PATHS]
)
def test_a_cache_directory_that_is_not_an_absolute_path_refuses(
    python_plan, tmp_path, value: str
) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    with pytest.raises(ResolverError):
        pip_download_argv(staged, value, python="python3")


def test_a_relative_program_with_a_separator_refuses(python_plan, tmp_path) -> None:
    """A bare name resolves on the jail's PATH; ``../npm`` resolves on the cwd."""
    staged = stage_python_plan(python_plan, tmp_path)
    with pytest.raises(ResolverError, match="bare program name"):
        pip_download_argv(staged, tmp_path / "cache", python="../python3")


def test_the_index_url_cannot_be_redirected(python_plan, tmp_path) -> None:
    staged = stage_python_plan(python_plan, tmp_path)
    with pytest.raises(ResolverError, match="must be exactly"):
        pip_download_argv(
            staged, tmp_path / "cache", python="python3",
            index_url="https://evil.example/simple",
        )


# ──────────────────────────────────────────────────────────────────────────────
# The environment
# ──────────────────────────────────────────────────────────────────────────────


def test_the_environment_is_exactly_these_seven(tmp_path) -> None:
    built = resolver_environment(tmp_path, str(tmp_path / "bin"))
    assert built == {
        "HOME": str(tmp_path),
        "PATH": str(tmp_path / "bin"),
        "LANG": "C.UTF-8",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    }


def test_resolver_disables_real_pip_global_user_and_site_config(tmp_path, monkeypatch):
    from pip._internal import configuration
    from pip._internal.exceptions import ConfigurationError

    files = {}
    expected = {}
    for kind, section in (
        (configuration.kinds.GLOBAL, "global"),
        (configuration.kinds.USER, "install"),
        (configuration.kinds.SITE, "download"),
    ):
        fixture = tmp_path / (kind + ".ini")
        value = "https://" + kind + ".invalid/simple"
        fixture.write_text(f"[{section}]\nindex-url = {value}\n", encoding="utf-8")
        files[kind] = [str(fixture)]
        expected[section + ".index-url"] = value
    monkeypatch.setattr(configuration, "get_configuration_files", lambda: files)
    monkeypatch.delenv("PIP_CONFIG_FILE", raising=False)

    # Isolated does not prevent global/site files from changing the index.
    control = configuration.Configuration(isolated=True)
    control.load()
    assert control.get_value("global.index-url") == expected["global.index-url"]
    assert control.get_value("download.index-url") == expected["download.index-url"]
    with pytest.raises(ConfigurationError):
        control.get_value("install.index-url")

    built = resolver_environment(tmp_path, str(tmp_path / "bin"))
    assert built["PIP_CONFIG_FILE"] == os.devnull
    monkeypatch.setenv("PIP_CONFIG_FILE", built["PIP_CONFIG_FILE"])
    isolated = configuration.Configuration(isolated=True)
    isolated.load()
    assert dict(isolated.items()) == {}


def test_resolver_environment_does_not_inherit_host_settings(tmp_path, monkeypatch):
    clean = resolver_environment(tmp_path, str(tmp_path / "bin"))
    for key in ("PIP_CONFIG_FILE", "PIP_INDEX_URL", "HTTPS_PROXY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(key, "host-value-must-not-reach-child")
    assert resolver_environment(tmp_path, str(tmp_path / "bin")) == clean


def test_the_environment_refuses_a_home_or_path_it_cannot_vouch_for(tmp_path) -> None:
    with pytest.raises(ResolverError, match="must be absolute"):
        resolver_environment("home", str(tmp_path))
    with pytest.raises(ResolverError, match="PATH"):
        resolver_environment(tmp_path, "")
    with pytest.raises(ResolverError, match="PATH entry must be absolute"):
        resolver_environment(tmp_path, "bin")


def test_the_module_reads_no_ambient_configuration() -> None:
    """``resolver_environment`` builds the child's env from nothing; the scan
    below is what proves this module never reads its own.

    The name of that function contains the substring the scan looks for, so the
    scan is written as "every occurrence must be part of an identifier we chose"
    rather than "the substring is absent" -- a blunt absence check would have
    forced the function to be called something less clear.
    """
    source = pathlib.Path(wr.__file__).read_text(encoding="utf-8")
    for token in ("subprocess", "urllib", "socket", "getenv", "os.environ", "eval("):
        assert token not in source, token
    allowed = ("resolver_environment", "the child's environment", "environment")
    index = 0
    while True:
        index = source.find("environ", index)
        if index < 0:
            break
        window = source[max(0, index - 40) : index + 40]
        assert any(name in window for name in allowed), window
        index += 1
