"""Table-driven tests for the workspace provisioning admission grammar.

Every refusal case asserts the exact ``reason`` and ``line_no``, because the sink maps
a reason to one actionable failure class (design D6) and shows the host the line. A test
that only asserted "it raised" would let two different defects pass as one another.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from tinyassets import workspace_provision as wp
from tinyassets.workspace_provision import (
    ProvisionRefused,
    admit_manifest_bytes,
    admit_node,
    admit_requirements,
)

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
SRI_512 = "sha512-" + "A" * 86 + "=="
SRI_512_OTHER = "sha512-" + "B" * 86 + "=="
SRI_256 = "sha256-" + "B" * 43 + "="
REGISTRY = "https://registry.npmjs.org/"


# ----------------------------------------------------------------------------------
# The refusal type itself
# ----------------------------------------------------------------------------------


def test_refusal_code_is_the_sink_failure_class() -> None:
    assert ProvisionRefused.code == "workspace_provision_refused"
    error = ProvisionRefused("unpinned", "pkg", line_no=7)
    assert error.code == "workspace_provision_refused"
    assert error.reason == "unpinned"
    assert error.line_no == 7
    assert error.detail == "pkg"
    assert "workspace_provision_refused" in str(error)


def test_unknown_reason_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown provisioning refusal reason"):
        ProvisionRefused("not_a_reason", "x")


def test_detail_is_truncated_and_never_carries_userinfo() -> None:
    long_line = "pkg==1.0 " + "z" * 500
    error = ProvisionRefused("unpinned", long_line)
    assert len(error.detail) == wp.MAX_DETAIL_CHARS

    with pytest.raises(ProvisionRefused) as caught:
        admit_requirements("pkg @ https://oauth2:hunter2@example.com/pkg.whl\n")
    assert caught.value.reason == "direct_url"
    assert "hunter2" not in caught.value.detail
    assert "[redacted]@" in caught.value.detail


def test_detail_strips_control_characters() -> None:
    error = ProvisionRefused("option_line", "--index-url \x1b[31mred\x07")
    assert "\x1b" not in error.detail
    assert "\x07" not in error.detail


# ----------------------------------------------------------------------------------
# Python: refused lines
# ----------------------------------------------------------------------------------

REFUSED_PYTHON: list[tuple[str, str, str, int | None]] = [
    ("editable", "-e .", "option_line", 1),
    ("index_url", "--index-url https://pypi.org/simple", "option_line", 1),
    ("find_links", "--find-links /wheels", "option_line", 1),
    ("bare_hash_line", "--hash=" + HASH_A, "option_line", 1),
    ("requirement_short", "-r other.txt", "include", 1),
    ("requirement_long", "--requirement=other.txt", "include", 1),
    ("constraint_short", "-c constraints.txt", "include", 1),
    ("constraint_long", "--constraint constraints.txt", "include", 1),
    ("pep508_direct", "pkg @ https://example.com/pkg.whl", "direct_url", 1),
    ("bare_url", "https://example.com/pkg.whl", "direct_url", 1),
    ("file_url", "pkg @ file:///wheels/pkg.whl", "direct_url", 1),
    ("git_scheme", "git+https://github.com/a/b#egg=c", "vcs", 1),
    ("hg_scheme", "hg+https://example.com/a", "vcs", 1),
    ("svn_scheme", "svn+https://example.com/a", "vcs", 1),
    ("bzr_scheme", "bzr+lp:example", "vcs", 1),
    ("relative_path", "./local/pkg", "local_path", 1),
    ("parent_path", "../pkg", "local_path", 1),
    ("absolute_path", "/opt/wheels/pkg", "local_path", 1),
    ("windows_path", "C:\\wheels\\pkg", "local_path", 1),
    ("home_path", "~/wheels/pkg", "local_path", 1),
    ("greater_equal", f"pkg>=1.0 --hash={HASH_A}", "unpinned", 1),
    ("compatible", f"pkg~=1.0 --hash={HASH_A}", "unpinned", 1),
    ("arbitrary_equality", f"pkg===1.0 --hash={HASH_A}", "unpinned", 1),
    ("not_equal", f"pkg!=1.0 --hash={HASH_A}", "unpinned", 1),
    ("bare_name", f"pkg --hash={HASH_A}", "unpinned", 1),
    ("wildcard", f"pkg==1.0.* --hash={HASH_A}", "unpinned", 1),
    ("two_specifiers", f"pkg==1.0,!=1.1 --hash={HASH_A}", "unpinned", 1),
    ("empty_version", f"pkg== --hash={HASH_A}", "unpinned", 1),
    ("not_a_version", f"pkg==one.point.oh --hash={HASH_A}", "unpinned", 1),
    ("no_hash", "pkg==1.0", "missing_hash", 1),
    ("wrong_algorithm", "pkg==1.0 --hash=md5:abcdef", "missing_hash", 1),
    ("short_hash", "pkg==1.0 --hash=sha256:abcd", "missing_hash", 1),
    ("uppercase_hash", "pkg==1.0 --hash=sha256:" + "A" * 64, "missing_hash", 1),
    ("dangling_hash_flag", "pkg==1.0 --hash", "missing_hash", 1),
    (
        "marker_platform_release",
        f'pkg==1.0 ; platform_release > "5" --hash={HASH_A}',
        "bad_marker",
        1,
    ),
    ("marker_extra", f'pkg==1.0 ; extra == "dev" --hash={HASH_A}', "bad_marker", 1),
    (
        "marker_platform_version",
        f'pkg==1.0 ; platform_version == "x" --hash={HASH_A}',
        "bad_marker",
        1,
    ),
    ("marker_unknown_variable", f'pkg==1.0 ; foo_bar == "x" --hash={HASH_A}', "bad_marker", 1),
    ("marker_missing_operator", f"pkg==1.0 ; python_version --hash={HASH_A}", "bad_marker", 1),
    (
        "marker_trailing_and",
        f'pkg==1.0 ; python_version == "3.11" and --hash={HASH_A}',
        "bad_marker",
        1,
    ),
    ("marker_in_operator", f'pkg==1.0 ; python_version in "3" --hash={HASH_A}', "bad_marker", 1),
    (
        "marker_unbalanced_paren",
        f'pkg==1.0 ; (python_version == "3.11" --hash={HASH_A}',
        "bad_marker",
        1,
    ),
    ("marker_empty", f"pkg==1.0 ; --hash={HASH_A}", "bad_marker", 1),
    (
        "marker_variable_to_variable",
        f"pkg==1.0 ; python_version == sys_platform --hash={HASH_A}",
        "bad_marker",
        1,
    ),
    ("leading_underscore_name", f"_pkg==1.0 --hash={HASH_A}", "bad_name", 1),
    ("empty_extras", f"pkg[]==1.0 --hash={HASH_A}", "bad_name", 1),
    ("blank_extra", f"pkg[a,,b]==1.0 --hash={HASH_A}", "bad_name", 1),
    ("space_in_name", f"pkg name==1.0 --hash={HASH_A}", "bad_name", 1),
    ("env_reference_alone", "${PACKAGE_PIN}", "env_reference", 1),
    (
        "env_reference_in_option",
        "--index-url https://${NPM_TOKEN}@example.com/simple",
        "env_reference",
        1,
    ),
    ("third_line", f"pkg==1.0 --hash={HASH_A}\n\n-r other.txt", "include", 3),
    (
        "continuation_reports_first_line",
        f"# lead comment\npkg>=1.0 \\\n    --hash={HASH_A}",
        "unpinned",
        2,
    ),
    (
        "conflicting_duplicate",
        f"pkg==1.0 --hash={HASH_A}\npkg==2.0 --hash={HASH_B}",
        "unpinned",
        2,
    ),
]


@pytest.mark.parametrize(
    ("text", "reason", "line_no"),
    [
        pytest.param(text, reason, line_no, id=name)
        for name, text, reason, line_no in REFUSED_PYTHON
    ],
)
def test_refused_python_lines(text: str, reason: str, line_no: int | None) -> None:
    with pytest.raises(ProvisionRefused) as caught:
        admit_requirements(text)
    assert caught.value.reason == reason
    assert caught.value.line_no == line_no
    assert caught.value.code == "workspace_provision_refused"


def test_refused_reasons_are_all_in_the_closed_set() -> None:
    for _name, _text, reason, _line in REFUSED_PYTHON:
        assert reason in wp.REFUSAL_REASONS


def test_hash_refusal_details_name_the_problem() -> None:
    with pytest.raises(ProvisionRefused) as caught:
        admit_requirements("pkg==1.0 --hash=md5:abcdef")
    assert "unsupported hash algorithm: md5" in caught.value.detail

    with pytest.raises(ProvisionRefused) as caught:
        admit_requirements("pkg==1.0 --hash=sha256:abcd")
    assert "malformed sha256 digest" in caught.value.detail


def test_requirements_over_max_bytes_have_no_line_number() -> None:
    with pytest.raises(ProvisionRefused) as caught:
        admit_requirements(f"pkg==1.0 --hash={HASH_A}\n", max_bytes=8)
    assert caught.value.reason == "too_large"
    assert caught.value.line_no is None


def test_requirements_rejects_non_text() -> None:
    with pytest.raises(TypeError):
        admit_requirements(b"pkg==1.0")  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------
# Python: admitted lines
# ----------------------------------------------------------------------------------


def test_admits_a_plain_pin() -> None:
    plan = admit_requirements(f"pkg==1.0 --hash={HASH_A}\n")
    (record,) = plan.records
    assert record.name == "pkg"
    assert record.extras == ()
    assert record.version == "1.0"
    assert record.marker is None
    assert record.hashes == (HASH_A,)


def test_admits_and_normalizes_name_and_extras() -> None:
    plan = admit_requirements(f"Pkg_Name.Two[Extra]==1.0 --hash={HASH_A}\n")
    (record,) = plan.records
    assert record.name == "pkg-name-two"
    assert record.extras == ("extra",)


def test_admits_multiple_extras_in_canonical_order() -> None:
    plan = admit_requirements(f"pkg[b,a]==1.0 --hash={HASH_A}\n")
    (record,) = plan.records
    assert record.extras == ("a", "b")
    assert plan.normalized_text == f"pkg[a,b]==1.0 --hash={HASH_A}\n"


@pytest.mark.parametrize(
    "written",
    ["1.0", "v1.0", "1.0-1", "2.0RC1", "1.0.0+local.1", "1!2.0", "2.0.dev3"],
)
def test_admits_pep440_versions_verbatim(written: str) -> None:
    """packaging decides whether the pin is valid; the text is passed through as written.

    The version is never rewritten to its normalized form: that would hand pip a
    string the manifest never wrote, and the wheel filename the hash pins is built
    from the version as the project published it.
    """
    plan = admit_requirements(f"pkg=={written} --hash={HASH_A}\n")
    assert plan.records[0].version == written


def test_admits_a_marker() -> None:
    plan = admit_requirements(f'pkg==1.0 ; python_version >= "3.11" --hash={HASH_A}\n')
    (record,) = plan.records
    assert record.marker == 'python_version >= "3.11"'


@pytest.mark.parametrize(
    "marker",
    [
        'python_version >= "3.11"',
        'python_full_version >= "3.11.2"',
        'sys_platform == "linux"',
        'platform_machine == "x86_64"',
        'platform_system == "Linux"',
        'implementation_name == "cpython"',
        'os_name == "posix"',
    ],
)
def test_admits_every_allowed_marker_variable(marker: str) -> None:
    plan = admit_requirements(f"pkg==1.0 ; {marker} --hash={HASH_A}\n")
    assert plan.records[0].marker == marker


def test_admits_a_compound_marker_with_parentheses() -> None:
    text = (
        'pkg==2.0rc1 ; sys_platform == "linux" and '
        '(python_version < "3.13" or implementation_name == "cpython") '
        f"--hash={HASH_A}\n"
    )
    plan = admit_requirements(text)
    (record,) = plan.records
    assert record.version == "2.0rc1"
    assert record.marker is not None
    assert " and " in record.marker
    assert record.marker.count("(") == 1


def test_admits_two_hashes() -> None:
    plan = admit_requirements(f"pkg==1.0 --hash={HASH_B} --hash={HASH_A}\n")
    (record,) = plan.records
    assert record.hashes == (HASH_A, HASH_B)


def test_admits_continuation_lines() -> None:
    text = f"pkg==1.0 \\\n    --hash={HASH_A} \\\n    --hash={HASH_B}\n"
    plan = admit_requirements(text)
    (record,) = plan.records
    assert record.name == "pkg"
    assert record.hashes == (HASH_A, HASH_B)


def test_admits_comments_and_blank_lines() -> None:
    text = f"# pinned by the lock\n\npkg==1.0 --hash={HASH_A}  # keep\n\n"
    plan = admit_requirements(text)
    assert len(plan.records) == 1
    assert plan.normalized_text == f"pkg==1.0 --hash={HASH_A}\n"


def test_admits_two_records_for_one_name_under_different_markers() -> None:
    text = (
        f'pkg==1.0 ; python_version < "3.12" --hash={HASH_A}\n'
        f'pkg==2.0 ; python_version >= "3.12" --hash={HASH_B}\n'
    )
    plan = admit_requirements(text)
    assert len(plan.records) == 2


def test_identical_duplicate_lines_collapse() -> None:
    line = f"pkg==1.0 --hash={HASH_A}\n"
    plan = admit_requirements(line * 2)
    assert len(plan.records) == 1
    assert plan.normalized_text == line


# ----------------------------------------------------------------------------------
# Python: the normalized text is the only thing the resolver stages
# ----------------------------------------------------------------------------------


def _digest(text: str) -> str:
    return admit_requirements(text).digest


def test_digest_ignores_record_order() -> None:
    first = f"alpha==1.0 --hash={HASH_A}\nbeta==2.0 --hash={HASH_B}\n"
    second = f"beta==2.0 --hash={HASH_B}\nalpha==1.0 --hash={HASH_A}\n"
    assert _digest(first) == _digest(second)


def test_digest_ignores_comments_and_whitespace() -> None:
    plain = f"pkg==1.0 --hash={HASH_A}\n"
    decorated = f"\n#  a note\n   pkg==1.0    --hash={HASH_A}   # trailing\n\n"
    assert _digest(plain) == _digest(decorated)


def test_digest_ignores_extras_order() -> None:
    assert _digest(f"pkg[b,a]==1.0 --hash={HASH_A}") == _digest(f"pkg[a,b]==1.0 --hash={HASH_A}")


def test_digest_ignores_marker_quote_style() -> None:
    """``str(Marker)`` is the canonical marker, so quoting and spacing normalize."""
    single = f"pkg==1.0 ; sys_platform=='linux' --hash={HASH_A}"
    double = f'pkg==1.0 ; sys_platform == "linux" --hash={HASH_A}'
    assert _digest(single) == _digest(double)


def test_digest_distinguishes_version_spelling() -> None:
    """Two spellings of one release are two admitted texts, because neither is rewritten."""
    assert _digest(f"pkg==v1.0 --hash={HASH_A}") != _digest(f"pkg==1.0 --hash={HASH_A}")


def test_digest_ignores_marker_comparison_direction() -> None:
    """A literal-first comparison is flipped to variable-first, so one condition is
    one admitted text and one digest.
    """
    forward = f'pkg==1.0 ; python_version >= "3.11" --hash={HASH_A}'
    flipped = f'pkg==1.0 ; "3.11" <= python_version --hash={HASH_A}'
    assert _digest(forward) == _digest(flipped)


def test_flipped_marker_canonicalizes_to_variable_first() -> None:
    text = f'pkg==1.0 ; "3.11" <= python_version --hash={HASH_A}'
    plan = admit_requirements(text)
    assert plan.records[0].marker == 'python_version >= "3.11"'


def test_digest_ignores_and_operand_order() -> None:
    """``and``/``or`` are commutative, so their operands are ordered before hashing."""
    first = f'pkg==1.0 ; sys_platform == "linux" and python_version >= "3.11" --hash={HASH_A}'
    second = f'pkg==1.0 ; python_version >= "3.11" and sys_platform == "linux" --hash={HASH_A}'
    assert _digest(first) == _digest(second)


def test_digest_changes_when_a_hash_changes() -> None:
    assert _digest(f"pkg==1.0 --hash={HASH_A}") != _digest(f"pkg==1.0 --hash={HASH_B}")


def test_digest_changes_when_a_version_changes() -> None:
    assert _digest(f"pkg==1.0 --hash={HASH_A}") != _digest(f"pkg==1.1 --hash={HASH_A}")


def test_digest_changes_when_a_hash_is_added() -> None:
    one = f"pkg==1.0 --hash={HASH_A}"
    two = f"pkg==1.0 --hash={HASH_A} --hash={HASH_B}"
    assert _digest(one) != _digest(two)


def test_digest_covers_exactly_the_normalized_text() -> None:
    import hashlib

    plan = admit_requirements(f"pkg[b,a]==v1.0 --hash={HASH_B} --hash={HASH_A}\n")
    assert plan.digest == hashlib.sha256(plan.normalized_text.encode("utf-8")).hexdigest()


def test_normalized_text_is_itself_admissible() -> None:
    text = f"pkg[b,a]==1.0 ; sys_platform=='linux' --hash={HASH_B} --hash={HASH_A}\n"
    plan = admit_requirements(text)
    second = admit_requirements(plan.normalized_text)
    assert second.normalized_text == plan.normalized_text
    assert second.digest == plan.digest


# ----------------------------------------------------------------------------------
# Shared byte-level admission
# ----------------------------------------------------------------------------------


def test_manifest_bytes_admits_plain_utf8() -> None:
    assert admit_manifest_bytes(b"pkg==1.0\n", max_bytes=64) == "pkg==1.0\n"


def test_manifest_bytes_strips_a_bom() -> None:
    data = "pkg==1.0\n".encode("utf-8-sig")
    assert admit_manifest_bytes(data, max_bytes=64) == "pkg==1.0\n"


def test_manifest_bytes_refuses_over_size() -> None:
    with pytest.raises(ProvisionRefused) as caught:
        admit_manifest_bytes(b"x" * 100, max_bytes=10)
    assert caught.value.reason == "too_large"


def test_manifest_bytes_refuses_nul() -> None:
    with pytest.raises(ProvisionRefused) as caught:
        admit_manifest_bytes(b"pkg\x00==1.0", max_bytes=64)
    assert caught.value.reason == "not_utf8"
    assert "offset 3" in caught.value.detail


def test_manifest_bytes_refuses_invalid_utf8() -> None:
    with pytest.raises(ProvisionRefused) as caught:
        admit_manifest_bytes(b"pkg\xff==1.0", max_bytes=64)
    assert caught.value.reason == "not_utf8"


def test_manifest_bytes_rejects_non_bytes() -> None:
    with pytest.raises(TypeError):
        admit_manifest_bytes("pkg==1.0", max_bytes=64)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------
# Node helpers
# ----------------------------------------------------------------------------------


def _manifest(**overrides: object) -> str:
    base: dict[str, object] = {
        "name": "app",
        "version": "1.0.0",
        "dependencies": {"left-pad": "^1.3.0"},
    }
    base.update(overrides)
    return json.dumps(base)


def _entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "version": "1.3.0",
        "resolved": f"{REGISTRY}left-pad/-/left-pad-1.3.0.tgz",
        "integrity": SRI_512,
    }
    entry.update(overrides)
    return entry


def _lockfile(
    packages: dict[str, object] | None = None,
    *,
    version: int | str = 3,
    root: dict[str, object] | None = None,
    **top_level: object,
) -> str:
    entries: dict[str, object] = {
        "": root
        if root is not None
        else {"name": "app", "version": "1.0.0", "dependencies": {"left-pad": "^1.3.0"}},
    }
    entries.update({"node_modules/left-pad": _entry()} if packages is None else packages)
    document: dict[str, object] = {
        "name": "app",
        "version": "1.0.0",
        "lockfileVersion": version,
        "packages": entries,
    }
    document.update(top_level)
    return json.dumps(document)


# ----------------------------------------------------------------------------------
# Node: admitted
# ----------------------------------------------------------------------------------


def test_admits_a_v3_lockfile() -> None:
    plan = admit_node(_manifest(), _lockfile())
    assert plan.lockfile_version == 3
    (package,) = plan.packages
    assert package.name == "left-pad"
    assert package.version == "1.3.0"
    assert package.resolved.startswith(REGISTRY)
    assert package.integrity == SRI_512
    assert len(plan.digest) == 64


def test_admits_a_v2_lockfile() -> None:
    plan = admit_node(_manifest(), _lockfile(version=2))
    assert plan.lockfile_version == 2


def test_admits_a_nested_and_scoped_entry() -> None:
    packages = {
        "node_modules/left-pad": _entry(),
        "node_modules/@scope/dep": _entry(
            version="2.0.0", resolved=f"{REGISTRY}@scope/dep/-/dep-2.0.0.tgz"
        ),
        "node_modules/left-pad/node_modules/inner": _entry(
            version="0.1.0", resolved=f"{REGISTRY}inner/-/inner-0.1.0.tgz"
        ),
    }
    plan = admit_node(_manifest(), _lockfile(packages))
    assert [package.name for package in plan.packages] == ["@scope/dep", "inner", "left-pad"]


def test_admits_an_entry_declaring_its_own_semver_dependencies() -> None:
    packages = {
        "node_modules/left-pad": _entry(
            dependencies={"inner": "^0.1.0"},
            peerDependencies={"react": ">=17 <19"},
            optionalDependencies={"fsevents": "~2.3.2"},
        ),
        "node_modules/inner": _entry(
            version="0.1.0", resolved=f"{REGISTRY}inner/-/inner-0.1.0.tgz"
        ),
    }
    plan = admit_node(_manifest(), _lockfile(packages))
    assert len(plan.packages) == 2


def test_admits_an_optional_peer_absent_from_the_lockfile() -> None:
    manifest = _manifest(
        peerDependencies={"react": "^18.0.0"},
        peerDependenciesMeta={"react": {"optional": True}},
    )
    plan = admit_node(manifest, _lockfile())
    assert len(plan.packages) == 1


def test_node_digest_ignores_key_order_but_not_content() -> None:
    manifest = _manifest()
    reordered = json.dumps(json.loads(manifest), sort_keys=False, indent=2)
    baseline = admit_node(manifest, _lockfile()).digest
    assert admit_node(reordered, _lockfile()).digest == baseline

    changed = {"node_modules/left-pad": _entry(integrity=SRI_512_OTHER)}
    assert admit_node(manifest, _lockfile(changed)).digest != baseline


def test_node_digest_covers_exactly_the_two_normalized_texts() -> None:
    import hashlib

    plan = admit_node(_manifest(), _lockfile())
    expected = hashlib.sha256(
        plan.normalized_package_json.encode("utf-8")
        + b"\x00"
        + plan.normalized_lockfile.encode("utf-8")
    ).hexdigest()
    assert plan.digest == expected


def test_node_normalized_text_round_trips() -> None:
    plan = admit_node(_manifest(), _lockfile())
    again = admit_node(plan.normalized_package_json, plan.normalized_lockfile)
    assert again.digest == plan.digest


# ----------------------------------------------------------------------------------
# Node: refused, one case per reason
# ----------------------------------------------------------------------------------


def _refusal(manifest: str, lockfile: str | None, **kwargs: int) -> ProvisionRefused:
    with pytest.raises(ProvisionRefused) as caught:
        admit_node(manifest, lockfile, **kwargs)  # type: ignore[arg-type]
    assert caught.value.line_no is None
    return caught.value


def test_node_requires_a_lockfile() -> None:
    assert _refusal(_manifest(), None).reason == "missing_lockfile"
    assert _refusal(_manifest(), "   ").reason == "missing_lockfile"


@pytest.mark.parametrize("version", [1, 4, "3", None, True])
def test_node_refuses_unsupported_lockfile_versions(version: object) -> None:
    error = _refusal(_manifest(), _lockfile(version=version))  # type: ignore[arg-type]
    assert error.reason == "lockfile_version"


def test_node_refuses_a_lockfile_without_a_packages_map() -> None:
    lockfile = json.dumps({"lockfileVersion": 3, "dependencies": {}})
    assert _refusal(_manifest(), lockfile).reason == "lockfile_version"


@pytest.mark.parametrize(
    ("manifest", "lockfile"),
    [
        pytest.param("{", None, id="manifest_truncated"),
        pytest.param("[]", None, id="manifest_not_an_object"),
        pytest.param(_manifest(), "{", id="lockfile_truncated"),
        pytest.param('{"name": "app", "name": "other"}', None, id="duplicate_key"),
        pytest.param('{"name": NaN}', None, id="non_finite_number"),
    ],
)
def test_node_refuses_bad_json(manifest: str, lockfile: str | None) -> None:
    assert _refusal(manifest, lockfile or _lockfile()).reason == "bad_json"


def test_node_refuses_over_size() -> None:
    error = _refusal(_manifest(), _lockfile(), max_bytes=16)
    assert error.reason == "too_large"


NODE_RESOLVED_REFUSALS: list[tuple[str, str, str]] = [
    (
        "evil_lookalike_host",
        "https://registry.npmjs.org.evil.com/left-pad/-/left-pad-1.3.0.tgz",
        "non_registry_resolution",
    ),
    (
        "other_registry",
        "https://registry.example.com/left-pad/-/left-pad-1.3.0.tgz",
        "non_registry_resolution",
    ),
    (
        "evil_suffix_host",
        "https://evilregistry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz",
        "non_registry_resolution",
    ),
    (
        "attacker_subdomain",
        "https://cdn.registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz",
        "non_registry_resolution",
    ),
    (
        "registry_on_another_port",
        "https://registry.npmjs.org:8443/left-pad/-/left-pad-1.3.0.tgz",
        "non_registry_resolution",
    ),
    (
        "not_a_tarball",
        "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.zip",
        "non_registry_resolution",
    ),
    (
        "carries_a_query",
        "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz?token=abc",
        "non_registry_resolution",
    ),
    ("plain_http", "http://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz", "url_dependency"),
    ("ftp", "ftp://example.com/left-pad.tgz", "url_dependency"),
    ("schemeless", "registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz", "url_dependency"),
    ("file", "file:../left-pad", "file_dependency"),
    ("git_https", "git+https://github.com/a/left-pad.git", "git_dependency"),
    ("git_ssh", "git+ssh://git@github.com/a/left-pad.git", "git_dependency"),
    ("github_shorthand", "github:a/left-pad", "git_dependency"),
]


@pytest.mark.parametrize(
    ("resolved", "reason"),
    [pytest.param(url, reason, id=name) for name, url, reason in NODE_RESOLVED_REFUSALS],
)
def test_node_refuses_non_registry_resolutions(resolved: str, reason: str) -> None:
    packages = {"node_modules/left-pad": _entry(resolved=resolved)}
    assert _refusal(_manifest(), _lockfile(packages)).reason == reason


def test_node_refuses_a_registry_prefix_without_the_trailing_slash() -> None:
    packages = {"node_modules/left-pad": _entry(resolved="https://registry.npmjs.orgx/a.tgz")}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "non_registry_resolution"


def test_node_refuses_the_registry_prefix_smuggled_inside_another_url() -> None:
    """The registry must be the host, not a substring of the URL."""
    smuggled = f"https://evil.example.com/proxy?u={REGISTRY}left-pad/-/left-pad-1.3.0.tgz"
    packages = {"node_modules/left-pad": _entry(resolved=smuggled)}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "non_registry_resolution"


def test_node_refuses_a_registry_url_with_userinfo_without_echoing_it() -> None:
    packages = {
        "node_modules/left-pad": _entry(
            resolved="https://s3cr3t-token@registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz"
        )
    }
    error = _refusal(_manifest(), _lockfile(packages))
    assert error.reason == "non_registry_resolution"
    assert "s3cr3t-token" not in error.detail
    assert "userinfo" in error.detail


def test_node_refuses_a_missing_resolved() -> None:
    packages = {"node_modules/left-pad": {"version": "1.3.0", "integrity": SRI_512}}
    error = _refusal(_manifest(), _lockfile(packages))
    assert error.reason == "non_registry_resolution"
    assert "no resolved" in error.detail


def test_node_refuses_a_missing_integrity() -> None:
    entry = _entry()
    del entry["integrity"]
    error = _refusal(_manifest(), _lockfile({"node_modules/left-pad": entry}))
    assert error.reason == "non_registry_resolution"
    assert "no integrity" in error.detail


def test_node_refuses_a_sha256_integrity_naming_the_algorithm() -> None:
    packages = {"node_modules/left-pad": _entry(integrity=SRI_256)}
    error = _refusal(_manifest(), _lockfile(packages))
    assert error.reason == "non_registry_resolution"
    assert "integrity algorithm" in error.detail
    assert "sha256" in error.detail


@pytest.mark.parametrize(
    "integrity", ["", "sha1-abcdef", "sha384-abcdef", "sha512-tooshort", "sha512", None, 5]
)
def test_node_refuses_a_bad_integrity(integrity: object) -> None:
    packages = {"node_modules/left-pad": _entry(integrity=integrity)}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "non_registry_resolution"


def test_node_refuses_an_unpinned_lockfile_entry() -> None:
    packages = {"node_modules/left-pad": _entry(version="^1.3.0")}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "unpinned"


def test_node_refuses_a_linked_entry() -> None:
    packages = {"node_modules/left-pad": {"link": True, "resolved": "packages/left-pad"}}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "workspace_dependency"


def test_node_refuses_an_entry_outside_node_modules() -> None:
    packages = {"node_modules/left-pad": _entry(), "packages/app": _entry()}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "workspace_dependency"


def test_node_refuses_manifest_workspaces() -> None:
    manifest = _manifest(workspaces=["packages/*"])
    assert _refusal(manifest, _lockfile()).reason == "workspace_dependency"


def test_node_refuses_lockfile_workspaces() -> None:
    error = _refusal(_manifest(), _lockfile(workspaces=["packages/*"]))
    assert error.reason == "workspace_dependency"
    assert "package-lock.json" in error.detail


def test_node_refuses_workspaces_inside_a_lock_entry() -> None:
    packages = {"node_modules/left-pad": _entry(workspaces=["packages/*"])}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "workspace_dependency"


def test_node_refuses_workspaces_on_the_lockfile_root_entry() -> None:
    root = {"name": "app", "version": "1.0.0", "workspaces": ["packages/*"]}
    error = _refusal(_manifest(), _lockfile(root=root))
    assert error.reason == "workspace_dependency"
    assert "root entry" in error.detail


@pytest.mark.parametrize("field", ["bundleDependencies", "bundledDependencies"])
def test_node_refuses_bundled_dependencies(field: str) -> None:
    """Its own class: not pinned by the lockfile and not fetched from the registry."""
    manifest = _manifest(**{field: ["left-pad"]})
    error = _refusal(manifest, _lockfile())
    assert error.reason == "bundled_dependency"
    assert field in error.detail


def test_node_refuses_a_bad_lockfile_entry_name() -> None:
    packages = {"node_modules/left-pad": _entry(), "node_modules/.bin": _entry()}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "bad_name"


def test_node_refuses_a_bad_manifest_dependency_name() -> None:
    manifest = _manifest(dependencies={".evil": "^1.0.0"})
    assert _refusal(manifest, _lockfile()).reason == "bad_name"


NODE_RANGE_REFUSALS: list[tuple[str, str, str]] = [
    ("workspace_protocol", "workspace:*", "workspace_dependency"),
    ("link_protocol", "link:../left-pad", "workspace_dependency"),
    ("file_protocol", "file:../left-pad", "file_dependency"),
    ("relative_path", "./vendor/left-pad", "file_dependency"),
    ("git_url", "git+https://github.com/a/left-pad.git", "git_dependency"),
    ("git_ssh", "git@github.com:a/left-pad.git", "git_dependency"),
    ("github_shorthand", "github:a/left-pad", "git_dependency"),
    ("bare_shorthand", "a/left-pad", "git_dependency"),
    ("https_tarball", "https://example.com/left-pad.tgz", "url_dependency"),
    ("http_tarball", "http://example.com/left-pad.tgz", "url_dependency"),
    ("npm_alias", "npm:other-pad@^1.0.0", "non_registry_resolution"),
    ("empty_range", "   ", "non_registry_resolution"),
    ("not_a_range", "1.0.0 && rm -rf /", "git_dependency"),
]


@pytest.mark.parametrize(
    ("spec", "reason"),
    [pytest.param(spec, reason, id=name) for name, spec, reason in NODE_RANGE_REFUSALS],
)
def test_node_refuses_non_semver_dependency_specs(spec: str, reason: str) -> None:
    manifest = _manifest(dependencies={"left-pad": spec})
    assert _refusal(manifest, _lockfile()).reason == reason


@pytest.mark.parametrize(
    ("spec", "reason"),
    [pytest.param(spec, reason, id=name) for name, spec, reason in NODE_RANGE_REFUSALS],
)
def test_node_refuses_non_semver_specs_nested_in_a_lock_entry(spec: str, reason: str) -> None:
    """A transitive dependency can name a git URL the manifest never mentions."""
    packages = {"node_modules/left-pad": _entry(dependencies={"inner": spec})}
    assert _refusal(_manifest(), _lockfile(packages)).reason == reason


def test_node_refuses_a_non_semver_spec_on_the_lockfile_root_entry() -> None:
    root = {"name": "app", "version": "1.0.0", "dependencies": {"left-pad": "git+https://x/y"}}
    assert _refusal(_manifest(), _lockfile(root=root)).reason == "git_dependency"


@pytest.mark.parametrize("field", ["dependencies", "optionalDependencies", "peerDependencies"])
def test_node_refuses_a_lock_entry_dependency_block_that_is_not_an_object(field: str) -> None:
    packages = {"node_modules/left-pad": _entry(**{field: ["inner"]})}
    assert _refusal(_manifest(), _lockfile(packages)).reason == "bad_json"


def test_node_refuses_a_non_string_dependency_spec() -> None:
    manifest = _manifest(dependencies={"left-pad": 1})
    assert _refusal(manifest, _lockfile()).reason == "bad_json"


def test_node_refuses_a_dependency_block_that_is_not_an_object() -> None:
    manifest = _manifest(devDependencies=["left-pad"])
    assert _refusal(manifest, _lockfile()).reason == "bad_json"


@pytest.mark.parametrize(
    "field", ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]
)
def test_node_refuses_a_dependency_missing_from_the_lockfile(field: str) -> None:
    manifest = _manifest(**{field: {"absent-pkg": "^1.0.0"}})
    error = _refusal(manifest, _lockfile())
    assert error.reason == "non_registry_resolution"
    assert "not in lockfile" in error.detail
    assert "absent-pkg" in error.detail


def test_node_refuses_a_dependency_present_only_nested() -> None:
    packages = {"node_modules/other/node_modules/left-pad": _entry()}
    error = _refusal(_manifest(), _lockfile(packages))
    assert error.reason == "non_registry_resolution"
    assert "not in lockfile" in error.detail


def test_node_refusal_reasons_are_all_in_the_closed_set() -> None:
    reasons = {reason for _name, _value, reason in NODE_RANGE_REFUSALS}
    reasons |= {reason for _name, _value, reason in NODE_RESOLVED_REFUSALS}
    assert reasons <= wp.REFUSAL_REASONS


def test_every_declared_reason_is_reachable_or_documented() -> None:
    source = pathlib.Path(wp.__file__).read_text(encoding="utf-8")
    for reason in wp.REFUSAL_REASONS:
        assert f'"{reason}"' in source, reason


# ----------------------------------------------------------------------------------
# The module stays a parser
# ----------------------------------------------------------------------------------


# ``urllib.parse`` is allowed -- it splits a URL and does no I/O. Everything that could
# reach a process, a socket or the ambient configuration is not.
FORBIDDEN_IN_SOURCE = (
    "subprocess",
    "urllib.request",
    "urllib.error",
    "urlopen",
    "requests",
    "socket",
    "environ",
    "eval(",
    "exec(",
)


def test_module_source_touches_no_process_network_or_configuration() -> None:
    source = pathlib.Path(wp.__file__).read_text(encoding="utf-8")
    found = [token for token in FORBIDDEN_IN_SOURCE if token in source]
    assert found == [], f"admission module must stay a pure parser; found {found}"


def test_the_only_urllib_the_module_names_is_the_parser() -> None:
    source = pathlib.Path(wp.__file__).read_text(encoding="utf-8")
    for index in range(len(source)):
        if source.startswith("urllib", index):
            assert source.startswith("urllib.parse", index), source[index : index + 40]
