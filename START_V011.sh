#!/bin/sh
# macOS/Linux: run `sh START_V011.sh`; Windows users double-click START_V011.cmd.
set -eu
QUANT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$QUANT_ROOT"
UV_VERSION=0.9.5
PYTHON_VERSION=3.13.9
case "$(uname -s):$(uname -m)" in
  Darwin:arm64) ASSET=uv-aarch64-apple-darwin; SHA=dc098ff224d78ed418e121fd374f655949d2c7031a70f6f6604eaf016a130433 ;;
  Darwin:x86_64) ASSET=uv-x86_64-apple-darwin; SHA=58b1d4a25aa8ff99147c2550b33dcf730207fe7e0f9a0d5d36a1bbf36b845aca ;;
  Linux:x86_64) ASSET=uv-x86_64-unknown-linux-gnu; SHA=2cf10babba653310606f8b49876cfb679928669e7ddaa1fb41fb00ce73e64f66 ;;
  Linux:aarch64|Linux:arm64) ASSET=uv-aarch64-unknown-linux-gnu; SHA=9db0c2f6683099f86bfeea47f4134e915f382512278de95b2a0e625957594ff3 ;;
  *) echo 'Unsupported OS/architecture. Requires macOS or glibc Linux on x64/ARM64.' >&2; exit 1 ;;
esac
hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d ' ' -f 1
  else shasum -a 256 "$1" | cut -d ' ' -f 1; fi
}
BOOTSTRAP="$QUANT_ROOT/.cache/bootstrap/uv-$UV_VERSION-$ASSET"
mkdir -p "$BOOTSTRAP" "$QUANT_ROOT/outputs/launcher_logs"
LOG="$QUANT_ROOT/outputs/launcher_logs/launch-$(date +%Y%m%d-%H%M%S)-$$.log"
echo "Preparing environment and refreshing reports. Log: $LOG"
run_update() {
  ARCHIVE="$BOOTSTRAP/$ASSET.tar.gz"
  if [ ! -f "$ARCHIVE" ]; then
    curl --proto '=https' --tlsv1.2 --fail --location --retry 2 --connect-timeout 30 --max-time 240 \
      "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$ASSET.tar.gz" -o "$ARCHIVE.partial"
    [ "$(hash_file "$ARCHIVE.partial")" = "$SHA" ] || { echo 'Download checksum failed.' >&2; exit 1; }
    mv "$ARCHIVE.partial" "$ARCHIVE"
  fi
  [ "$(hash_file "$ARCHIVE")" = "$SHA" ] || { echo 'Cached archive checksum failed. Delete it and retry.' >&2; exit 1; }
  tar -xzf "$ARCHIVE" -C "$BOOTSTRAP"
  UV="$BOOTSTRAP/$ASSET/uv"
  # Include host, absolute project path and architecture; a copied venv is not reused.
  KEY_FILE="$BOOTSTRAP/runtime-key-$$.txt"
  MACHINE_ID=$(hostname)
  if [ -f /etc/machine-id ]; then MACHINE_ID="$MACHINE_ID|$(cat /etc/machine-id)"; fi
  if [ "$(uname -s)" = Darwin ]; then
    MACHINE_ID="$MACHINE_ID|$(ioreg -rd1 -c IOPlatformExpertDevice | awk -F '"' '/IOPlatformUUID/ {print $(NF-1)}')"
  fi
  printf '%s\n' "$QUANT_ROOT|$MACHINE_ID|$ASSET|$PYTHON_VERSION" > "$KEY_FILE"
  KEY=$(hash_file "$KEY_FILE" | cut -c 1-16)
  rm "$KEY_FILE"
  RUNTIME="$QUANT_ROOT/.cache/runtime/$KEY"
  export UV_PYTHON_INSTALL_DIR="$RUNTIME/python" UV_CACHE_DIR="$QUANT_ROOT/.cache/uv"
  export UV_PYTHON_PREFERENCE=only-managed UV_NO_PROGRESS=1 PYTHONUTF8=1
  "$UV" python install "$PYTHON_VERSION" --no-bin
  if [ ! -x "$RUNTIME/venv/bin/python" ]; then "$UV" venv --python "$PYTHON_VERSION" "$RUNTIME/venv"; fi
  PYTHON="$RUNTIME/venv/bin/python"
  "$PYTHON" -c 'import sys; assert sys.version_info[:3] == (3, 13, 9), sys.version'
  echo 'Installing or checking project dependencies...'
  "$UV" --quiet --quiet pip install --python "$PYTHON" --editable "$QUANT_ROOT"
  "$PYTHON" -m quant_research refresh --open "$@"
}
# A subshell with errexit preserves failures, unlike a pipeline through tee.
set +e
(set -e; run_update "$@") > "$LOG" 2>&1
RESULT=$?
set -e
cat "$LOG"
if [ "$RESULT" -ne 0 ]; then
  echo "Refresh failed. Check network access, disk space, and $LOG. Existing reports were preserved." >&2
fi
exit "$RESULT"
