#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DATE_EPOCH:?SOURCE_DATE_EPOCH must be provisioned for reproducible builds}"
: "${VERSION:?VERSION must be provisioned}"
: "${ARCHITECTURE:?ARCHITECTURE must be provisioned}"

repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo"
output="packaging/dist/linux"
case "$ARCHITECTURE" in
  x86_64) deb_arch="amd64" ;;
  arm64) deb_arch="arm64" ;;
  *)
    echo "unsupported Linux architecture: $ARCHITECTURE" >&2
    exit 1
    ;;
esac
python -m PyInstaller --noconfirm --clean \
  --distpath "$output" \
  --workpath packaging/build/linux \
  packaging/linux/TinyAssets.spec

portable="TinyAssets-${VERSION}-${ARCHITECTURE}"
portable_root="$output/$portable"
install -Dm755 "$output/tinyassets" "$portable_root/tinyassets"
install -Dm644 tinyassets/desktop/app.ico "$portable_root/tinyassets.ico"
tar --sort=name \
  "--mtime=@${SOURCE_DATE_EPOCH}" \
  --owner=0 --group=0 --numeric-owner \
  -C "$output" -czf "$output/${portable}.tar.gz" "$portable"

deb_root="$output/deb-root"
install -Dm755 "$output/tinyassets" "$deb_root/usr/bin/tinyassets"
install -Dm644 tinyassets/desktop/app.ico \
  "$deb_root/usr/share/icons/hicolor/256x256/apps/tinyassets.ico"
mkdir -p "$deb_root/DEBIAN"
cat > "$deb_root/DEBIAN/control" <<EOF
Package: tinyassets
Version: ${VERSION}
Architecture: ${deb_arch}
Maintainer: TinyAssets <jonathan.m.farnsworth@gmail.com>
Description: Goal-agnostic daemon host tray
Section: utils
Priority: optional
EOF
find "$deb_root" -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +
dpkg-deb --root-owner-group --build "$deb_root" \
  "$output/tinyassets_${VERSION}_${deb_arch}.deb"
