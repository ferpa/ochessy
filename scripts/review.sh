#!/usr/bin/env bash
# Review a Chess.com game with Stockfish and show the report in a pager.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
USERNAME=""
TIME_CLASS="auto"
DEPTH="12"
LEELA_SECONDS="0"
LEELA_POSITIONS="5"
MOVE_TIME="0"
GAME_URL=""
INDEX="0"

usage() {
  echo "Usage: review.sh --username NAME [--depth N] [--game-url URL] [--index N] [--leela-seconds N] [--leela-positions N]"
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
    --depth)
      DEPTH="${2:-12}"
      shift 2
      ;;
    --leela-seconds)
      LEELA_SECONDS="${2:-0}"
      shift 2
      ;;
    --leela-positions)
      LEELA_POSITIONS="${2:-5}"
      shift 2
      ;;
    --move-time)
      MOVE_TIME="${2:-0}"
      shift 2
      ;;
    --game-url)
      GAME_URL="${2:-}"
      shift 2
      ;;
    --index)
      INDEX="${2:-0}"
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

if [[ -z $USERNAME ]]; then
  echo "Set a Chess.com username on the OChessy panel first."
  echo
  read -r -p "Press Enter to close."
  exit 2
fi

missing=()
command -v python3 >/dev/null 2>&1 || missing+=(python)
if ! command -v stockfish >/dev/null 2>&1 && [[ ! -x ${HOME}/.local/bin/stockfish ]]; then
  missing+=(stockfish)
fi
if ! python3 -c "import chess, chess.engine, chess.pgn" >/dev/null 2>&1; then
  missing+=(python-chess)
fi

if ((${#missing[@]} > 0)); then
  echo "OChessy needs: ${missing[*]}"
  echo "Install with: omarchy pkg aur add stockfish python-chess"
  echo
  read -r -p "Press Enter to close."
  exit 1
fi

REPORT="$(mktemp /tmp/ochessy-review.XXXXXX.txt)"
cleanup() { rm -f "$REPORT"; }
trap cleanup EXIT

argv=(python3 "$SCRIPT_DIR/ochessy.py" review
  --username "$USERNAME"
  --time-class "$TIME_CLASS"
  --depth "$DEPTH"
  --leela-seconds "$LEELA_SECONDS"
  --leela-positions "$LEELA_POSITIONS"
  --move-time "$MOVE_TIME"
  --index "$INDEX"
  --output "$REPORT")
if [[ -n $GAME_URL ]]; then
  argv+=(--game-url "$GAME_URL")
fi

set +e
"${argv[@]}"
status=$?
set -e

if [[ $status -ne 0 || ! -s $REPORT ]]; then
  echo
  read -r -p "Press Enter to close."
  exit "$status"
fi

if command -v less >/dev/null 2>&1; then
  less -R "$REPORT"
else
  cat "$REPORT"
  echo
  read -r -p "Press Enter to close."
fi
