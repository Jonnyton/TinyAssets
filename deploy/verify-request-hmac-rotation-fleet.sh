#!/usr/bin/env bash
# Prove the exact request-HMAC worker boundary across deploy quiescence.

set -euo pipefail

WORKERS=(
    tinyassets-worker
    tinyassets-worker-codex-2
    tinyassets-worker-claude-1
    tinyassets-worker-claude-2
)
RUNTIME_CONTAINERS=(tinyassets-daemon "${WORKERS[@]}")

usage() {
    echo "usage: $0 {capture <image-ref>|assert-quiesced <worker-id>...}" >&2
    exit 2
}

validate_id() {
    local container_id="$1"
    [[ "${container_id}" =~ ^[0-9a-f]{64}$ ]] || {
        echo "::error::malformed worker identity" >&2
        exit 1
    }
}

validate_image_ref() {
    local image_ref="$1"
    [[ "${image_ref}" =~ ^ghcr\.io/[a-z0-9._-]+/tinyassets-daemon@sha256:[0-9a-f]{64}$ ]] || {
        echo "::error::malformed immutable correction image reference" >&2
        exit 1
    }
}

assert_no_minting_authority() {
    local container="$1"
    local container_ref="$2"
    local configured_environment
    local entry
    configured_environment="$(
        docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' \
            "${container_ref}" 2>/dev/null
    )" || {
        echo "::error::${container} configured environment is unavailable" >&2
        exit 1
    }
    while IFS= read -r entry; do
        case "${entry}" in
            TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=*)
                echo "::error::${container} exposes request admission minting authority" >&2
                exit 1
                ;;
        esac
    done <<< "${configured_environment}"
}

capture() {
    [ "$#" -eq 1 ] || usage
    local expected_image="$1"
    validate_image_ref "${expected_image}"
    local container
    local container_id
    local running
    local configured_image
    local extra
    local identity_state
    local current_id
    local captured_names=()
    local captured_ids=()
    local worker_ids=()
    local index
    for container in "${RUNTIME_CONTAINERS[@]}"; do
        identity_state="$(
            docker inspect -f '{{.Id}} {{.State.Running}} {{.Config.Image}}' \
                "${container}" 2>/dev/null
        )" || {
            echo "::error::${container} is absent before rotation quiescence" >&2
            exit 1
        }
        read -r container_id running configured_image extra <<< "${identity_state}"
        validate_id "${container_id}"
        if [ -n "${extra:-}" ] || [ "${configured_image}" != "${expected_image}" ]; then
            echo "::error::${container} does not run the exact correction image" >&2
            exit 1
        fi
        if [ "${running}" != "true" ]; then
            echo "::error::${container} is not running before rotation quiescence" >&2
            exit 1
        fi
        if [ "${container}" != "tinyassets-daemon" ]; then
            assert_no_minting_authority "${container}" "${container_id}"
            worker_ids+=("${container_id}")
        fi
        current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} disappeared during rotation capture" >&2
            exit 1
        }
        if [ "${current_id}" != "${container_id}" ]; then
            echo "::error::${container} identity changed during rotation capture" >&2
            exit 1
        fi
        captured_names+=("${container}")
        captured_ids+=("${container_id}")
    done
    for index in "${!captured_names[@]}"; do
        container="${captured_names[${index}]}"
        container_id="${captured_ids[${index}]}"
        current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} disappeared during rotation capture" >&2
            exit 1
        }
        if [ "${current_id}" != "${container_id}" ]; then
            echo "::error::${container} identity changed during rotation capture" >&2
            exit 1
        fi
    done
    printf '%s\n' "${worker_ids[@]}"
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
    local returned_id
    local extra
    local identity_state
    local expected_ids=("$@")
    for index in "${!WORKERS[@]}"; do
        container="${WORKERS[$index]}"
        expected_id="${expected_ids[$index]}"
        validate_id "${expected_id}"
        identity_state="$(
            docker inspect -f '{{.Id}} {{.State.Running}}' \
                "${expected_id}" 2>/dev/null
        )" || {
            echo "::error::${container} pinned identity disappeared after rotation quiescence" >&2
            exit 1
        }
        read -r returned_id running extra <<< "${identity_state}"
        if [ -n "${extra:-}" ] || [ "${returned_id}" != "${expected_id}" ]; then
            echo "::error::${container} pinned identity is malformed after rotation quiescence" >&2
            exit 1
        fi
        current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} disappeared after rotation quiescence" >&2
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
    for index in "${!WORKERS[@]}"; do
        container="${WORKERS[$index]}"
        expected_id="${expected_ids[$index]}"
        current_id="$(docker inspect -f '{{.Id}}' "${container}" 2>/dev/null)" || {
            echo "::error::${container} disappeared after rotation quiescence" >&2
            exit 1
        }
        if [ "${current_id}" != "${expected_id}" ]; then
            echo "::error::${container} identity changed during rotation quiescence" >&2
            exit 1
        fi
    done
}

[ "$#" -ge 1 ] || usage
command="$1"
shift
case "${command}" in
    capture)
        capture "$@"
        ;;
    assert-quiesced)
        assert_quiesced "$@"
        ;;
    *)
        usage
        ;;
esac
