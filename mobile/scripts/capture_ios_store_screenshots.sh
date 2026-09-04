#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 APP_PATH OUTPUT_DIR" >&2
  exit 2
fi

app_path="$1"
output_dir="$2"
mkdir -p "$output_dir"

if [[ ! -d "$app_path" ]]; then
  echo "::error::simulator app bundle does not exist: $app_path"
  exit 1
fi

runtime_id="$({ xcrun simctl list runtimes -j || exit 1; } | python3 -c '
import json, re, sys

runtimes = json.load(sys.stdin)["runtimes"]
available = [
    runtime for runtime in runtimes
    if runtime.get("isAvailable")
    and runtime.get("identifier", "").startswith("com.apple.CoreSimulator.SimRuntime.iOS-")
]
if not available:
    raise SystemExit("no available iOS Simulator runtime")

def version(runtime):
    return tuple(int(part) for part in re.findall(r"\d+", runtime.get("version", "0")))

print(max(available, key=version)["identifier"])
')"

device_types_json="$(xcrun simctl list devicetypes -j)"
created_udids=()

cleanup() {
  for udid in "${created_udids[@]}"; do
    xcrun simctl shutdown "$udid" >/dev/null 2>&1 || true
    xcrun simctl delete "$udid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

create_device() {
  local label="$1"
  shift
  local type_id
  local udid

  for device_name in "$@"; do
    type_id="$(DEVICE_NAME="$device_name" python3 -c '
import json, os, sys

needle = os.environ["DEVICE_NAME"]
for device in json.load(sys.stdin)["devicetypes"]:
    if device.get("name") == needle:
        print(device["identifier"])
        break
' <<<"$device_types_json")"
    [[ -n "$type_id" ]] || continue
    if udid="$(xcrun simctl create "TinyAssets Store $label" "$type_id" "$runtime_id" 2>/dev/null)"; then
      created_udids+=("$udid")
      CREATED_UDID="$udid"
      return 0
    fi
  done

  echo "::error::no Apple simulator device type could produce the required $label screenshot" >&2
  return 1
}

CREATED_UDID=""
create_device "6.5-inch iPhone" \
  "iPhone 14 Plus" \
  "iPhone 13 Pro Max" \
  "iPhone 12 Pro Max" \
  "iPhone 11 Pro Max" \
  "iPhone XS Max"
iphone_udid="$CREATED_UDID"

create_device "13-inch iPad" \
  "iPad Pro 13-inch (M5)" \
  "iPad Pro 13-inch (M4)" \
  "iPad Pro (12.9-inch) (6th generation)" \
  "iPad Pro (12.9-inch) (5th generation)"
ipad_udid="$CREATED_UDID"

capture() {
  local udid="$1"
  local filename="$2"
  local accepted_sizes="$3"

  xcrun simctl boot "$udid"
  xcrun simctl bootstatus "$udid" -b
  xcrun simctl status_bar "$udid" override \
    --time 9:41 \
    --operatorName "" \
    --wifiBars 3 \
    --cellularBars 4 \
    --batteryState charged \
    --batteryLevel 100 || true
  xcrun simctl install "$udid" "$app_path"
  xcrun simctl launch --terminate-running-process "$udid" io.tinyassets.app
  sleep 20

  local screenshot="$output_dir/$filename"
  # JPEG preserves the native simulator dimensions while guaranteeing the
  # alpha-free image Apple requires for store screenshots.
  xcrun simctl io "$udid" screenshot --type=jpeg "$screenshot"

  local width
  local height
  local alpha
  width="$(sips -g pixelWidth "$screenshot" | awk '/pixelWidth:/ {print $2}')"
  height="$(sips -g pixelHeight "$screenshot" | awk '/pixelHeight:/ {print $2}')"
  alpha="$(sips -g hasAlpha "$screenshot" | awk '/hasAlpha:/ {print tolower($2)}')"
  local actual="${width}x${height}"

  if [[ ",${accepted_sizes}," != *",${actual},"* ]]; then
    echo "::error::$filename is $actual; Apple accepts only $accepted_sizes"
    return 1
  fi
  if [[ "$alpha" != "no" ]]; then
    echo "::error::$filename has an alpha channel"
    return 1
  fi

  echo "$filename: $actual, no alpha"
  xcrun simctl shutdown "$udid"
}

capture "$iphone_udid" "iphone-6.5.jpg" "1242x2688,1284x2778"
capture "$ipad_udid" "ipad-13.jpg" "2048x2732,2064x2752"
