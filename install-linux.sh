#!/usr/bin/env bash
# One-line installer / updater for Linux (and macOS):
#
#   curl -fsSL https://raw.githubusercontent.com/mrtipeq/PolarnikTTS/main/install-linux.sh | bash
#
# Downloads PolarnikTTS into ~/PolarnikTTS (as the current user - never run it with sudo),
# keeps an existing config.yaml, voices, models and engine environments, then runs install.sh,
# which creates the Python environment and registers the launcher in Chrome/Chromium.
set -euo pipefail

REPO="${POLARNIK_REPO:-mrtipeq/PolarnikTTS}"
BRANCH="${POLARNIK_BRANCH:-main}"
DEST="${POLARNIK_DIR:-$HOME/PolarnikTTS}"
TARBALL="${POLARNIK_TARBALL:-}"          # local archive instead of downloading (offline / testing)

if [ "$(id -u)" = "0" ] && [ -z "${POLARNIK_ALLOW_ROOT:-}" ]; then
  echo "Please do not run this with sudo - PolarnikTTS installs into your own home folder."
  exit 1
fi
for tool in tar; do command -v "$tool" >/dev/null || { echo "Missing tool: $tool"; exit 1; }; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [ -z "$TARBALL" ]; then
  URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"
  echo "Downloading PolarnikTTS ($REPO, $BRANCH)..."
  if command -v curl >/dev/null; then curl -fsSL "$URL" -o "$TMP/src.tar.gz"
  elif command -v wget >/dev/null; then wget -qO "$TMP/src.tar.gz" "$URL"
  else echo "Install curl or wget first (e.g. sudo apt install curl)"; exit 1; fi
  TARBALL="$TMP/src.tar.gz"
fi

mkdir -p "$TMP/src"
tar -xzf "$TARBALL" -C "$TMP/src"
SRC="$(find "$TMP/src" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -f "$SRC/install.sh" ] || { echo "The archive does not contain PolarnikTTS"; exit 1; }

# Stop a running server so its files can be replaced
pkill -f -- "-m polarnik_server" 2>/dev/null || true

mkdir -p "$DEST"
# Copy the new files over the installation; user data is never overwritten
( cd "$SRC" && find . -type f \
    ! -path "./server/config.yaml" ! -path "./server/.venv/*" ! -path "./server/envs/*" \
    ! -path "./server/models/*" ! -path "./server/voices/*" ! -path "./server/logs/*" ! -path "./server/cache/*" \
    -print0 ) | while IFS= read -r -d '' f; do
  mkdir -p "$DEST/$(dirname "$f")"
  cp -f "$SRC/$f" "$DEST/$f"
done
echo "PolarnikTTS files are in $DEST"

exec bash "$DEST/install.sh"
