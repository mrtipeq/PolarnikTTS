#!/usr/bin/env bash
# Starts the PolarnikTTS engine server using server/.venv and server/config.yaml.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$ROOT/server"
VPY="$SERVER/.venv/bin/python"
[ -x "$VPY" ] || { echo "Virtualenv not found - run ./install.sh first."; exit 1; }
cd "$SERVER"
exec "$VPY" -m polarnik_server --config "$SERVER/config.yaml" "$@"
