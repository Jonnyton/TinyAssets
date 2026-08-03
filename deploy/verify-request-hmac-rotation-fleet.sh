#!/usr/bin/env bash
# Prove the exact request-HMAC worker boundary across deploy quiescence.

set -euo pipefail

WORKERS=(
    tinyassets-worker
    tinyassets-worker-codex-2
    tinyassets-worker-claude-1
    tinyassets-worker-claude-2
)

usage() {
    echo "usage: $0 {capture|assert-quiesced <worker-id>...}" >&2
    exit 2
}

validate_id() {
    local container_id="$1"
    [[ "${container_id}" =~ ^[0-9a-f]{64}$ ]] || {
        echo "::error::malformed worker identity" >&2
        exit 1
    }
}

capture() {
    local container
    local container_id
    local running
    for container in "${WORKERS[@]}"; do
        container_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} is absent before rotation quiescence" >&2
            exit 1
        }
        validate_id "${container_id}"
        running="$(docker inspect -f '{{.State.Running}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} state is unavailable before rotation quiescence" >&2
            exit 1
        }
        if [ "${running}" != "true" ]; then
            echo "::error::${container} is not running before rotation quiescence" >&2
            exit 1
        fi
        if ! docker exec "${container}" python -c \
            'import os, sys; sys.exit(1 if "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" in os.environ else 0)'; then
            echo "::error::${container} exposes request admission minting authority" >&2
            exit 1
        fi
        printf '%s\n' "${container_id}"
    done
}

assert_quiesced() {
    if [ "$#" -ne "${#WORKERS[@]}" ]; then
        echo "::error::incomplete pre-quiescence worker identity set" >&2
        exit 1
    fi

    local index
    local container
    local expected_id
    local current_id
    local running
    local expected_ids=("$@")
    for index in "${!WORKERS[@]}"; do
        container="${WORKERS[$index]}"
        expected_id="${expected_ids[$index]}"
        validate_id "${expected_id}"
        current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} disappeared after rotation quiescence" >&2
            exit 1
        }
        running="$(docker inspect -f '{{.State.Running}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} state is unavailable after rotation quiescence" >&2
            exit 1
        }
        if [ "${current_id}" != "${expected_id}" ]; then
            echo "::error::${container} identity changed during rotation quiescence" >&2
            exit 1
        fi
        if [ "${running}" != "false" ]; then
            echo "::error::${container} is not quiesced before key transmission" >&2
            exit 1
        fi
    done
}

[ "$#" -ge 1 ] || usage
command="$1"
shift
case "${command}" in
    capture)
        [ "$#" -eq 0 ] || usage
        capture
        ;;
    assert-quiesced)
        assert_quiesced "$@"
        ;;
    *)
        usage
        ;;
esac
