#!/usr/bin/env bash
# Machine-readable Chess.com status for the ochessy bar panel.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
USERNAME=""
TIME_CLASS="auto"

usage() {
  echo "Usage: status.sh [--username NAME] [--time-class auto|bullet|blitz|rapid|daily]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username)
      USERNAME="${2:-}"
      shift 2
      ;;
    --time-class)
      TIME_CLASS="${2:-auto}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

exec python3 "$SCRIPT_DIR/ochessy.py" status --username "$USERNAME" --time-class "$TIME_CLASS"
