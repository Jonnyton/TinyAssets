# Diagnostic image only. This does not change production's browser toolchain.
# Use the already-built local oracle as --build-arg ORACLE_IMAGE=... .
ARG ORACLE_IMAGE
FROM ${ORACLE_IMAGE}
USER root
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends chromium fonts-liberation \
    && chromium --version \
    && rm -rf /var/lib/apt/lists/*
# Match the daemon's non-root uid. No host credentials or home is mounted.
USER 1001:1001
