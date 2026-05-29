# Dockerfile for the Workflow daemon (MCP server).
#
# Per docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md Row A:
# provider-agnostic container image that ships to Fly.io, Hetzner, or any
# Linux host. No Fly-specific config baked in; that lives in Row D.
#
# Build:
#     docker build -t workflow-daemon .
#
# Run (local smoke):
#     docker run -p 8001:8001 \
#       -v $(pwd)/data:/data \
#       -e WORKFLOW_DATA_DIR=/data \
#       workflow-daemon
#
# MCP initialize probe (after run):
#     curl -sS -X POST http://localhost:8001/mcp \
#       -H "Content-Type: application/json" \
#       -H "Accept: application/json, text/event-stream" \
#       -d '{"jsonrpc":"2.0","id":1,"method":"initialize",
#            "params":{"protocolVersion":"2024-11-05","capabilities":{},
#                      "clientInfo":{"name":"probe","version":"1.0"}}}'
#
# Image is multi-stage: builder layer installs native-compilation deps,
# final layer stays slim (no build-essential).

# ---------- Stage 1: builder ----------

FROM python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a9fc0e6e38295747e49ac0 AS builder

ARG TARGETARCH
ARG NODEJS_VERSION=20.20.2-1nodesource1
ARG CODEX_CLI_VERSION=0.135.0
ARG NODESOURCE_REPO_CHECKSUM=b42e0321dabdc24e892115da705cf061167eac12a317f23d329862d0aa0a271d
ARG RUSTUP_VERSION=1.28.2
ARG RUSTUP_SHA256_AMD64=20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c
ARG RUSTUP_SHA256_ARM64=e3853c5a252fca15252d07cb23a1bdd9377a8c6f3efa01531109281ae47f841c
ARG RUST_TOOLCHAIN=1.85.1

# Native build-deps for lancedb (rust), clingo (cmake), spacy (cython),
# and general C extensions. Removed from the final image.
# Node.js 20 LTS via nodesource — Debian's default apt nodejs is too old
# (Node 12/18) for @openai/codex which requires Node ≥ 18; nodesource 20
# is the smallest LTS that's known-compatible and widely battle-tested.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        gnupg \
        pkg-config \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        -o /tmp/nodesource-repo.gpg.key \
    && echo "${NODESOURCE_REPO_CHECKSUM}  /tmp/nodesource-repo.gpg.key" | sha256sum -c - \
    && gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg /tmp/nodesource-repo.gpg.key \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs="${NODEJS_VERSION}" \
    && rm -f /tmp/nodesource-repo.gpg.key \
    && rm -rf /var/lib/apt/lists/*

# Install rust toolchain for lancedb wheels that lack pre-built linux
# binaries. Pinned to known-good rustup + toolchain versions; bump when
# lancedb upgrades.
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN set -e; \
    case "${TARGETARCH}" in \
      amd64) rustup_arch="x86_64-unknown-linux-gnu"; rustup_sha="${RUSTUP_SHA256_AMD64}" ;; \
      arm64) rustup_arch="aarch64-unknown-linux-gnu"; rustup_sha="${RUSTUP_SHA256_ARM64}" ;; \
      *) echo "unsupported TARGETARCH for pinned rustup: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl --proto '=https' --tlsv1.2 -fsSL \
        "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/${rustup_arch}/rustup-init" \
        -o /tmp/rustup-init; \
    echo "${rustup_sha}  /tmp/rustup-init" | sha256sum -c -; \
    chmod 0755 /tmp/rustup-init; \
    /tmp/rustup-init -y --default-toolchain "${RUST_TOOLCHAIN}" --profile minimal; \
    rm -f /tmp/rustup-init

# Install codex CLI to an explicit prefix so the path is deterministic
# across distros. npm global prefix under nodesource Debian may be
# /usr/lib/node_modules (not /usr/local/lib), so we pin to /opt/codex-install
# — then COPY --from=builder targets a known path.
#
# Smoke-test the install via the absolute path. The final-stage image
# does NOT symlink the bare codex bin to /usr/local/bin; it copies the
# flock wrapper there instead (see below). Adding the same wrapper in
# the builder stage would just be dead weight, so we run the binary
# directly here.
RUN mkdir -p /opt/codex-install && \
    npm install --prefix /opt/codex-install "@openai/codex@${CODEX_CLI_VERSION}" && \
    /opt/codex-install/node_modules/.bin/codex --version

WORKDIR /build

# Copy project metadata + source so editable install works.
COPY pyproject.toml ./
COPY PLAN.md ./
COPY workflow/ ./workflow/
COPY domains/ ./domains/
# fantasy_daemon is the node-execution runtime invoked by
# workflow.cloud_worker. Without it in the image, the cloud worker
# supervisor crash-loops with `No module named fantasy_daemon`.
COPY fantasy_daemon/ ./fantasy_daemon/

# Install into a venv that we'll copy to the final stage. Keeps the
# final image free of pip metadata + build tools.
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -e ".[mcp,gemini,groq,grok]"

# ---------- Stage 2: final ----------

FROM python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a9fc0e6e38295747e49ac0

ARG NODEJS_VERSION=20.20.2-1nodesource1
ARG GH_VERSION=2.93.0
ARG NODESOURCE_REPO_CHECKSUM=b42e0321dabdc24e892115da705cf061167eac12a317f23d329862d0aa0a271d

# Runtime-only deps. No build-essential here.
# libgomp1 is a common transitive native dep for numpy/scipy-backed
# packages (spacy, lancedb); include it proactively.
# Node.js 20 LTS via nodesource — same version as builder so the copied
# codex binary's native addons are ABI-compatible. No npm needed at
# runtime; the codex module tree is COPY'd from the builder.
#
# GitHub CLI (gh) — the github_pull_request effector shells out to
# `gh pr create` (workflow/effectors/github_pr.py). Without gh on the
# runtime PATH the effector fails with error_kind=gh_not_installed
# (BUG-110), which blocks every real PR open from the patch-request loop.
# Installed from cli.github.com before curl is purged below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bubblewrap \
        ca-certificates \
        curl \
        gnupg \
        libgomp1 \
        tini \
        util-linux \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        -o /tmp/nodesource-repo.gpg.key \
    && echo "${NODESOURCE_REPO_CHECKSUM}  /tmp/nodesource-repo.gpg.key" | sha256sum -c - \
    && gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg /tmp/nodesource-repo.gpg.key \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs="${NODEJS_VERSION}" \
    && apt-get install -y --no-install-recommends gh="${GH_VERSION}" \
    && apt-get purge -y curl gnupg \
    && rm -f /tmp/nodesource-repo.gpg.key \
    && rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 1001 workflow && \
    useradd --system --uid 1001 --gid workflow --home /app --shell /bin/bash workflow

# Copy the codex install tree from builder and install the flock
# wrapper as /usr/local/bin/codex. The wrapper takes an exclusive
# flock on a sentinel in /app/.codex before exec'ing the real codex
# binary — required because PR #965 binds the codex auth directory
# across the daemon + worker containers, and Codex's official CI/CD
# auth guide forbids sharing one auth.json across concurrent runners
# without serialization (concurrent refresh attempts race rotation
# and trigger `refresh_token_reused`). See deploy/codex-flock-wrapper.sh.
COPY --from=builder /opt/codex-install /opt/codex-install
COPY deploy/codex-flock-wrapper.sh /usr/local/bin/codex
RUN chmod 0755 /usr/local/bin/codex && \
    /usr/local/bin/codex --version

WORKDIR /app

# Copy the populated venv + source from the builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/workflow /app/workflow
COPY --from=builder /build/domains /app/domains
COPY --from=builder /build/fantasy_daemon /app/fantasy_daemon
COPY --from=builder /build/pyproject.toml /app/pyproject.toml
COPY --from=builder /build/PLAN.md /app/PLAN.md

# Static data files required at runtime.
# world_rules.lp is the ASP constraint program; asp_engine.py resolves it
# relative to the package root (parents[2]/data/). The *.db files in data/
# are runtime state and live in WORKFLOW_DATA_DIR, not here.
COPY data/world_rules.lp /app/data/world_rules.lp

# Stdlib-only MCP canary — reused across Layer-1 (local), tier-3 GHA,
# docker-build CI, cloud canary, and the compose.yml container-health
# healthcheck. Single definition of "healthy MCP" across every probe
# surface. Copied directly (not via the builder stage) because the
# script is pure stdlib — no compilation needed.
COPY scripts/mcp_public_canary.py /app/scripts/mcp_public_canary.py
COPY deploy/docker-entrypoint.sh /app/docker-entrypoint.sh

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Data directory — Row B will wire WORKFLOW_DATA_DIR through all
# on-disk state. For now, /data is the expected bind-mount target;
# operators supply it via `-v /host/path:/data` + the env var below.
ENV WORKFLOW_DATA_DIR=/data
RUN mkdir -p /data && \
    chmod +x /app/docker-entrypoint.sh && \
    chown -R workflow:workflow /data /app

USER workflow

EXPOSE 8001

# tini as PID 1 handles signal forwarding + zombie reaping.
# docker-entrypoint.sh enforces cloud-daemon subscription-only auth,
# optionally installs a subscription Codex auth bundle, then execs the CMD.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]

# Default command — the FastMCP streamable-http server on 0.0.0.0:8001.
# Matches `if __name__ == "__main__": main()` in workflow/universe_server.py.
CMD ["python", "-m", "workflow.universe_server"]
