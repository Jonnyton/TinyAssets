import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
PYTHON_SCRIPT = re.compile(
    r"\bpython(?:3(?:\.\d+)?)?\s+[\"']?(scripts/[A-Za-z0-9_./-]+\.py)\b"
)


def test_workflow_python_script_paths_exist():
    references = [
        (workflow, script_path)
        for workflow in sorted(WORKFLOW_DIR.glob("*.yml"))
        for script_path in PYTHON_SCRIPT.findall(workflow.read_text(encoding="utf-8"))
    ]

    assert references, "no `python scripts/...` workflow references were found"

    missing = [
        f"{workflow.relative_to(REPO_ROOT)}: {script_path}"
        for workflow, script_path in references
        if not (REPO_ROOT / script_path).is_file()
    ]
    assert not missing, "workflow Python script path(s) do not exist:\n" + "\n".join(missing)
