#!/usr/bin/env bash
# Write the iOS AppIcon asset catalog from the square icon source.
#
# Run from `mobile/`, after `cap add/sync ios`. Both iOS workflows call this, so
# the release build and the PR compile-check cannot drift apart.
#
# Why this exists rather than `capacitor-assets generate --ios`:
#
#   * `cap add ios` writes Capacitor's blue placeholder icon. Nothing replaces it
#     unless something does so explicitly, so a correctly signed build otherwise
#     reaches TestFlight wearing the placeholder.
#   * Apple reads the App Store icon out of THIS catalog, inside the uploaded
#     build -- not from separately uploaded listing metadata. So it has to come
#     from the square source: `resources/icon.png` is the rounded badge, and Apple
#     applies its own mask on top, leaving dark wedges in the corners.
#   * `capacitor-assets` cannot run in CI at all. It needs sharp's native binary,
#     which `npm ci --ignore-scripts` never installs, so it dies with
#     "Cannot find module '../build/Release/sharp-*.node'" (Codex, 2026-09-03).
#
# Writing the catalog directly also makes provenance exact rather than inferred:
# the 1024 entry is byte-compared against the source, so no generator's
# source-selection order can quietly substitute a different file. `sips` ships
# with macOS, so the smaller entries need nothing installed.
set -euo pipefail

src="${1:-resources/icon-ios.png}"
appicon="${2:-ios/App/App/Assets.xcassets/AppIcon.appiconset}"
contents="$appicon/Contents.json"
entries="$(mktemp)"
trap 'rm -f "$entries"' EXIT

[ -f "$src" ] || { echo "::error::icon source $src missing"; exit 1; }
[ -f "$contents" ] || { echo "::error::$contents missing — catalog shape changed"; exit 1; }

# Each entry's pixel size is size x scale. Entries without a filename are
# unassigned slots, which Xcode permits; skip them rather than crashing.
python3 - "$contents" > "$entries" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
seen = set()
for img in data.get("images", []):
    name = img.get("filename")
    if not name or name in seen:
        continue
    seen.add(name)
    width = float(img["size"].split("x")[0])
    scale = float((img.get("scale") or "1x").rstrip("x"))
    print(f"{name} {int(round(width * scale))}")
PY

# python3 on a POSIX runner emits \n, so this cannot bite there -- but a trailing
# carriage return makes every size compare as a non-integer, and this repo has
# already lost time to exactly that class on the upload keystore.
tr -d '\r' < "$entries" > "$entries.clean" && mv "$entries.clean" "$entries"
[ -s "$entries" ] || { echo "::error::no icon entries in $contents"; exit 1; }

marketing=0
while read -r name px; do
  dest="$appicon/$name"
  if [ "$px" -eq 1024 ]; then
    # The source is exactly 1024, so copy it: the bytes Apple reads are the bytes
    # we rendered, and `cmp` proves it.
    cp "$src" "$dest"
    cmp -s "$src" "$dest" || { echo "::error::1024 icon does not match $src"; exit 1; }
    marketing=1
  else
    sips -s format png -z "$px" "$px" "$src" --out "$dest" > /dev/null
  fi
  got="$(sips -g pixelWidth "$dest" | awk '/pixelWidth/ {print $2}')"
  [ "$got" = "$px" ] || { echo "::error::$name is ${got}px, expected ${px}px"; exit 1; }
  echo "  $name ${px}px"
done < "$entries"

if [ "$marketing" -ne 1 ]; then
  echo "::error::no 1024 marketing entry in $contents — App Store Connect requires one"
  exit 1
fi
echo "app icon catalog written from $src (1024 entry byte-identical)"
