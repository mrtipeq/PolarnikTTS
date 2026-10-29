#!/usr/bin/env bash
# Installs the PolarnikTTS engine server on Linux/macOS.
#   ./install.sh                         # base + edge-tts + piper
#   EXTRAS=edge,piper,chatterbox ./install.sh   # GPU engines go to isolated envs (server/envs/<engine>)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$ROOT/server"
EXTRAS="${EXTRAS:-edge,piper}"
CUDA="${CUDA:-}"
PY="${PYTHON:-}"

if [ -z "$PY" ]; then
  for cand in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      v="$("$cand" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])')"
      if [ "$v" -ge 310 ]; then PY="$cand"; break; fi
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer was not found."
  echo "  Ubuntu / Debian / Mint:  sudo apt install python3 python3-venv python3-pip"
  echo "  Fedora:                  sudo dnf install python3"
  echo "  Arch / Manjaro:          sudo pacman -S python"
  echo "Install it and run the installer again."
  exit 1
fi
echo "Using Python: $PY"

VENV="$SERVER/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  rm -rf "$VENV"
  if ! "$PY" -m venv "$VENV"; then
    echo
    echo "Could not create a Python virtual environment - the venv module is missing."
    echo "  Ubuntu / Debian / Mint:  sudo apt install python3-venv"
    echo "Install it and run the installer again."
    exit 1
  fi
fi
VPY="$VENV/bin/python"
"$VPY" -m pip install --upgrade pip wheel >/dev/null

HEAVY=""
LIGHT=""
for x in $(echo "$EXTRAS" | tr ',' ' '); do
  case "$x" in chatterbox|xtts) HEAVY="$HEAVY $x" ;; *) LIGHT="$LIGHT,$x" ;; esac
done
LIGHT="${LIGHT#,}"; [ -n "$LIGHT" ] || LIGHT="edge"

echo "Installing server package with extras [$LIGHT]"
"$VPY" -m pip install -e "$SERVER[$LIGHT]"

if [ ! -f "$SERVER/config.yaml" ]; then
  cp "$SERVER/config.example.yaml" "$SERVER/config.yaml"
  echo "Created $SERVER/config.yaml - edit it to enable engines / API keys."
fi

case ",$EXTRAS," in
  *,piper,*|*,all,*)
    echo "Downloading Piper Polish voices"
    (cd "$SERVER" && "$VPY" scripts/download_models.py piper)
    ;;
esac

for h in $HEAVY; do
  echo "Installing $h into its isolated environment (several GB)"
  (cd "$SERVER" && "$VPY" scripts/install_engine.py "$h")
done

# Native messaging host (lets the extension start the server on demand)
EXT_ID="$(tr -d '[:space:]' < "$ROOT/host/EXTENSION_ID")"
HOST_SH="$ROOT/host/polarnik_host.sh"
printf '#!/usr/bin/env bash\nexec "%s" -u "%s" "$@"\n' "$VPY" "$SERVER/polarnik_host.py" > "$HOST_SH"
chmod +x "$HOST_SH"
for d in "$HOME/.config/google-chrome" "$HOME/.config/chromium" "$HOME/.config/microsoft-edge" "$HOME/.config/BraveSoftware/Brave-Browser" \
         "$HOME/Library/Application Support/Google/Chrome" "$HOME/Library/Application Support/Chromium"; do
  [ -d "$d" ] || continue
  mkdir -p "$d/NativeMessagingHosts"
  sed -e "s|__HOST_PATH__|$HOST_SH|" -e "s|__EXTENSION_ID__|$EXT_ID|" "$ROOT/host/pl.polarnik.launcher.json.template" \
    > "$d/NativeMessagingHosts/pl.polarnik.launcher.json"
  echo "Registered native messaging host in $d"
  REGISTERED=1
done
if [ -z "${REGISTERED:-}" ]; then
  echo
  echo "WARNING: no Chrome / Chromium / Edge / Brave profile found in ~/.config - the extension"
  echo "will not be able to start the server by itself. Start Chrome once and run the installer"
  echo "again. (Chromium from Snap or Flatpak does not support this at all - use the .deb/.rpm"
  echo "Google Chrome, or start the server with ./run_server.sh.)"
fi

echo
echo "Done. Start the server with: ./run_server.sh"
echo "Then load extension/ in Chrome: chrome://extensions -> Developer mode -> Load unpacked."
