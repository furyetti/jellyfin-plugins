#!/usr/bin/env bash
# Publish a built plugin zip to this catalog.
#
# Usage: scripts/publish.sh <slug> <version> <zip> [notes]
#   slug     folder under plugins/ (must already exist)
#   version  four-part plugin version, e.g. 0.0.0.27
#   zip      built plugin zip, plugin DLL at the zip root
#   notes    optional release notes
#
# Creates release <slug>-<version> with asset <slug>-<version>.zip, records the
# version, regenerates manifest.json/README.md, pushes, and verifies the
# published asset against the recorded checksum.
#
# Needs: python3, gh logged in as furyetti (or GH_TOKEN set), curl, md5sum.
set -euo pipefail

SLUG="${1:?usage: $0 <slug> <version> <zip> [notes]}"
VERSION="${2:?usage: $0 <slug> <version> <zip> [notes]}"
ZIP="${3:?usage: $0 <slug> <version> <zip> [notes]}"
NOTES="${4:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="furyetti/jellyfin-plugins"
TAG="$SLUG-$VERSION"
ASSET="$SLUG-$VERSION.zip"

[ -f "$ROOT/plugins/$SLUG/plugin.json" ] || { echo "unknown plugin '$SLUG' (no plugins/$SLUG/plugin.json)" >&2; exit 1; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must look like 0.0.0.27" >&2; exit 1; }
[ -f "$ZIP" ] || { echo "zip not found: $ZIP" >&2; exit 1; }
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "catalog repo has uncommitted changes; commit or discard them first" >&2
  exit 1
fi
export GH_TOKEN="${GH_TOKEN:-$(gh auth token --user furyetti)}"

git -C "$ROOT" pull -q --ff-only
python3 -I "$ROOT/scripts/catalog.py" build --check

# The asset name is part of the manifest URL, so upload a copy under that name.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp "$ZIP" "$STAGE/$ASSET"
CHECKSUM="$(md5sum "$STAGE/$ASSET" | awk '{print $1}')"

if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  gh release upload "$TAG" "$STAGE/$ASSET" -R "$REPO" --clobber
else
  gh release create "$TAG" "$STAGE/$ASSET" -R "$REPO" \
    --title "$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$ROOT/plugins/$SLUG/plugin.json") $VERSION" \
    --notes "${NOTES:-$SLUG $VERSION}"
fi

python3 -I "$ROOT/scripts/catalog.py" add-version "$SLUG" "$VERSION" "$CHECKSUM"
git -C "$ROOT" add plugins manifest.json README.md
git -C "$ROOT" commit -q -m "$SLUG $VERSION"
git -C "$ROOT" push -q

ACTUAL="$(curl -fsSL "https://github.com/$REPO/releases/download/$TAG/$ASSET" | md5sum | awk '{print $1}')"
if [ "$ACTUAL" != "$CHECKSUM" ]; then
  echo "published asset md5 $ACTUAL does not match recorded $CHECKSUM" >&2
  exit 1
fi
echo "Published $SLUG $VERSION (md5 $CHECKSUM)"
