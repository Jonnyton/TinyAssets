# The Linux oracle: what CI runs, on the dev box.
#
# A local Windows run is not an oracle on its own (AGENTS.md). Six CI rounds on
# the workspace change were spent on failures that could only exist on Linux:
# a test that skips on Windows keeps asserting a contract the code has already
# left, and the local suite stays green while doing so. This image is the same
# Python CI uses (3.11), plus the two things the sandbox actually needs and a
# Windows host cannot provide at all: bubblewrap, and POSIX descriptor
# semantics.
#
# Built by scripts/linux_oracle.py, which tags it with a hash of this file plus
# pyproject.toml, so a dependency change rebuilds it and nothing else does.
FROM python:3.11-slim

# git: the workspace sink shells to it, and several suites need a real repo.
# bubblewrap: the node sandbox jail - the two proofs that skip everywhere else.
# nodejs/npm: the provisioning grammar's fixtures.
# build-essential: source-only wheels in the dependency tree.
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        git bubblewrap nodejs npm build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies are baked into a layer keyed on pyproject.toml. The package
# itself is NOT installed here: the run mounts the working tree (uncommitted
# changes included, which is the point of a local oracle) and pytest imports it
# from the rootdir. Installing a stub here would shadow the tree under test.
COPY pyproject.toml /tmp/oracle/pyproject.toml
RUN python - <<'PY' > /tmp/oracle/requirements.txt
import tomllib

with open("/tmp/oracle/pyproject.toml", "rb") as handle:
    data = tomllib.load(handle)
project = data.get("project", {})
deps = list(project.get("dependencies", []))
deps += list(project.get("optional-dependencies", {}).get("dev", []))
print("\n".join(deps))
PY
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/oracle/requirements.txt

# The suite refuses a temp root inside the repo (tests/conftest.py), so give it
# one outside and make it explicit rather than inherited.
ENV TMPDIR=/tmp/oracle-tmp
RUN mkdir -p /tmp/oracle-tmp

WORKDIR /work
