#!/usr/bin/env python3
"""Chess.com stats fetch and local Stockfish review for the OChessy plugin."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

USER_AGENT = "OChessy/1.0 (Omarchy plugin; +https://omarchy.org)"
API_ROOT = "https://api.chess.com/pub"
API_HOST = "api.chess.com"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_BYTES = 1024
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,29}$")
ARCHIVE_PATH_RE = re.compile(r"^/pub/player/([a-z0-9][a-z0-9_-]{0,29})/games/\d{4}/\d{2}$")
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ochessy"
TIME_CLASSES = ("bullet", "blitz", "rapid", "daily")
DRAW_RESULTS = {
    "agreed",
    "stalemate",
    "repetition",
    "insufficient",
    "50move",
    "timevsinsufficient",
    "insufficientmaterial",
}
SCRIPT_DIR = Path(__file__).resolve().parent
LESSONS_PATH = SCRIPT_DIR / "lessons.json"

INACCURACY_CP = 50
MISTAKE_CP = 100
BLUNDER_CP = 300


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def read_cache(name: str, ttl: int) -> Any | None:
    path = cache_path(name)
    try:
        if path.stat().st_size > MAX_RESPONSE_BYTES:
            return None
        age = time.time() - path.stat().st_mtime
        if age > ttl:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(name: str, payload: Any) -> None:
    path = cache_path(name)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def require_username(value: str) -> str:
    user = normalize_username(value)
    if not user or not USERNAME_RE.fullmatch(user):
        raise RuntimeError("Invalid Chess.com username")
    return user


def allowed_chess_api_url(url: str, username: str) -> bool:
    if not username or not USERNAME_RE.fullmatch(username):
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    if parsed.netloc.lower() != API_HOST:
        return False
    if parsed.query or parsed.fragment or parsed.params or parsed.username or parsed.password:
        return False
    path = parsed.path.rstrip("/") or "/"
    prefix = f"/pub/player/{username}"
    if path in {prefix, f"{prefix}/stats", f"{prefix}/games/archives"}:
        return True
    match = ARCHIVE_PATH_RE.fullmatch(path)
    return bool(match and match.group(1) == username)


def allowed_archive_url(url: str, username: str) -> bool:
    if not allowed_chess_api_url(url, username):
        return False
    parsed = urlparse(url)
    match = ARCHIVE_PATH_RE.fullmatch(parsed.path.rstrip("/") or "/")
    return bool(match and match.group(1) == username)


def read_limited(fp: Any, limit: int) -> bytes:
    if fp is None:
        return b""
    data = fp.read(limit + 1)
    if not data:
        return b""
    if len(data) > limit:
        raise RuntimeError(f"HTTP body exceeded {limit} bytes")
    return data


def opener_for(username: str) -> urllib.request.OpenerDirector:
    class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            resolved = urljoin(req.full_url, newurl)
            if not allowed_chess_api_url(resolved, username):
                raise RuntimeError(f"Refusing redirect to {resolved}")
            return urllib.request.HTTPRedirectHandler.redirect_request(
                self, req, fp, code, msg, headers, newurl
            )

    return urllib.request.build_opener(RestrictedRedirect)


def http_get(url: str, username: str, accept: str = "application/json") -> bytes:
    if not allowed_chess_api_url(url, username):
        raise RuntimeError(f"Refusing non-Chess.com API URL: {url}")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )
    try:
        with opener_for(username).open(req, timeout=20) as resp:
            final_url = resp.geturl()
            if not allowed_chess_api_url(final_url, username):
                raise RuntimeError(f"Refusing non-Chess.com API URL: {final_url}")
            length = resp.headers.get("Content-Length")
            if length is not None:
                try:
                    if int(length) > MAX_RESPONSE_BYTES:
                        raise RuntimeError(f"HTTP response too large ({length} bytes)")
                except ValueError:
                    pass
            return read_limited(resp, MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        body = read_limited(exc, MAX_ERROR_BYTES).decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def api_get(url: str, cache_name: str, ttl: int, username: str, pause: float = 0.4) -> Any:
    cached = read_cache(cache_name, ttl)
    if cached is not None:
        return cached
    time.sleep(pause)
    payload = json.loads(http_get(url, username).decode("utf-8"))
    write_cache(cache_name, payload)
    return payload


def normalize_username(value: str) -> str:
    return str(value or "").strip().lstrip("@").lower()


def stockfish_path() -> str | None:
    found = shutil.which("stockfish")
    if found:
        return found
    home_local = Path.home() / ".local" / "bin" / "stockfish"
    if home_local.is_file() and os.access(home_local, os.X_OK):
        return str(home_local)
    for candidate in ("/usr/bin/stockfish", "/usr/local/bin/stockfish"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def missing_packages() -> list[str]:
    missing: list[str] = []
    if stockfish_path() is None:
        missing.append("stockfish")
    try:
        import chess  # noqa: F401
        import chess.engine  # noqa: F401
        import chess.pgn  # noqa: F401
    except ImportError:
        missing.append("python-chess")
    return missing


def country_code(profile: dict[str, Any]) -> str:
    country = str(profile.get("country") or "")
    if not country:
        return ""
    return country.rstrip("/").split("/")[-1].upper()


def player_side_name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("username") or "")
    text = str(side or "")
    if "/player/" in text:
        return text.rstrip("/").split("/")[-1]
    return text


def player_side_result(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("result") or "")
    return ""


def player_side_rating(side: Any) -> int:
    if isinstance(side, dict):
        try:
            return int(side.get("rating") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def classify_result(result: str) -> str:
    value = str(result or "").lower()
    if value == "win":
        return "win"
    if value in DRAW_RESULTS:
        return "draw"
    return "loss"


def parse_stats_block(block: Any) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {"rating": 0, "best": 0, "rd": 0, "last": 0, "record": {"win": 0, "loss": 0, "draw": 0}}
    last = block.get("last") if isinstance(block.get("last"), dict) else {}
    best = block.get("best") if isinstance(block.get("best"), dict) else {}
    record = block.get("record") if isinstance(block.get("record"), dict) else {}
    return {
        "rating": int(last.get("rating") or 0),
        "best": int(best.get("rating") or 0),
        "rd": int(last.get("rd") or 0),
        "last": int(last.get("date") or 0),
        "record": {
            "win": int(record.get("win") or 0),
            "loss": int(record.get("loss") or 0),
            "draw": int(record.get("draw") or 0),
        },
    }


def peak_rating_stats(stats: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    best_key = "blitz"
    best_block: dict[str, Any] = {}
    best_date = -1
    for key in TIME_CLASSES:
        block = parse_stats_block(stats.get(f"chess_{key}"))
        if block["last"] >= best_date and block["rating"] > 0:
            best_date = block["last"]
            best_key = key
            best_block = block
    return best_key, best_block


def pick_time_class(stats: dict[str, Any], requested: str, last_game: dict[str, Any] | None) -> str:
    key = str(requested or "auto").lower()
    if key in TIME_CLASSES:
        return key
    if last_game and last_game.get("timeClass") in TIME_CLASSES:
        return str(last_game["timeClass"])
    picked, _ = peak_rating_stats(stats)
    return picked


def summarize_game(raw: dict[str, Any], username: str) -> dict[str, Any] | None:
    white_name = player_side_name(raw.get("white")).lower()
    black_name = player_side_name(raw.get("black")).lower()
    user = username.lower()
    if user not in (white_name, black_name):
        return None
    rules = str(raw.get("rules") or "chess")
    if rules not in ("chess", ""):
        return None
    user_color = "white" if white_name == user else "black"
    side = raw.get("white") if user_color == "white" else raw.get("black")
    result = classify_result(player_side_result(side))
    opponent = black_name if user_color == "white" else white_name
    return {
        "url": str(raw.get("url") or ""),
        "endTime": int(raw.get("end_time") or 0),
        "timeClass": str(raw.get("time_class") or ""),
        "timeControl": str(raw.get("time_control") or ""),
        "rated": bool(raw.get("rated", True)),
        "white": white_name,
        "black": black_name,
        "whiteRating": player_side_rating(raw.get("white")),
        "blackRating": player_side_rating(raw.get("black")),
        "result": result,
        "userColor": user_color,
        "opponent": opponent,
        "fen": str(raw.get("fen") or ""),
        "pgn": str(raw.get("pgn") or ""),
    }


def fetch_profile(username: str) -> dict[str, Any]:
    user = require_username(username)
    return api_get(f"{API_ROOT}/player/{user}", f"player_{user}.json", ttl=300, username=user)


def fetch_stats(username: str) -> dict[str, Any]:
    user = require_username(username)
    return api_get(f"{API_ROOT}/player/{user}/stats", f"stats_{user}.json", ttl=180, username=user)


def fetch_archives(username: str) -> list[str]:
    user = require_username(username)
    payload = api_get(
        f"{API_ROOT}/player/{user}/games/archives",
        f"archives_{user}.json",
        ttl=600,
        username=user,
    )
    archives = payload.get("archives") if isinstance(payload, dict) else None
    allowed: list[str] = []
    for item in archives or []:
        url = str(item)
        if allowed_archive_url(url, user):
            allowed.append(url)
    return allowed


def fetch_month(archive_url: str, username: str) -> list[dict[str, Any]]:
    user = require_username(username)
    if not allowed_archive_url(archive_url, user):
        raise RuntimeError(f"Refusing non-Chess.com archive URL: {archive_url}")
    parts = archive_url.rstrip("/").split("/")
    stamp = "_".join(parts[-2:]) if len(parts) >= 2 else "month"
    if not re.fullmatch(r"\d{4}_\d{2}", stamp):
        raise RuntimeError(f"Refusing non-Chess.com archive URL: {archive_url}")
    now = datetime.now(timezone.utc)
    current = f"{now.year}_{now.month:02d}"
    ttl = 120 if stamp == current else 3600
    payload = api_get(archive_url, f"games_{user}_{stamp}.json", ttl=ttl, username=user)
    games = payload.get("games") if isinstance(payload, dict) else None
    return list(games or [])


def recent_games(username: str, limit: int = 10) -> list[dict[str, Any]]:
    archives = fetch_archives(username)
    collected: list[dict[str, Any]] = []
    for archive_url in reversed(archives[-3:]):
        for raw in reversed(fetch_month(archive_url, username)):
            summary = summarize_game(raw, username)
            if not summary:
                continue
            collected.append(summary)
            if len(collected) >= limit:
                return collected
    return collected


def find_game(username: str, game_url: str = "", index: int = 0) -> dict[str, Any]:
    games = recent_games(username, limit=20)
    if not games:
        raise RuntimeError("No completed standard games found in recent archives.")
    if game_url:
        wanted = game_url.rstrip("/").lower()
        for game in games:
            if str(game.get("url") or "").rstrip("/").lower() == wanted:
                return game
        raise RuntimeError(f"Game not found in recent archives: {game_url}")
    if index < 0 or index >= len(games):
        raise RuntimeError("Game index is out of range.")
    return games[index]


def status_payload(username: str, time_class: str) -> dict[str, Any]:
    missing = missing_packages()
    if not username:
        return {
            "ok": False,
            "ready": False,
            "username": "",
            "packagesOk": not missing,
            "missingPackages": missing,
            "lastError": "Set a Chess.com username",
            "games": [],
            "ratings": {},
            "record": {"win": 0, "loss": 0, "draw": 0},
        }

    profile = fetch_profile(username)
    stats = fetch_stats(username)
    games = recent_games(username, limit=10)
    last_game = games[0] if games else None
    selected = pick_time_class(stats, time_class, last_game)
    selected_block = parse_stats_block(stats.get(f"chess_{selected}"))
    ratings = {key: parse_stats_block(stats.get(f"chess_{key}")) for key in TIME_CLASSES}

    tactics = stats.get("tactics") if isinstance(stats.get("tactics"), dict) else {}
    lessons = stats.get("lessons") if isinstance(stats.get("lessons"), dict) else {}
    rush = stats.get("puzzle_rush") if isinstance(stats.get("puzzle_rush"), dict) else {}
    tactics_high = tactics.get("highest") if isinstance(tactics.get("highest"), dict) else {}
    tactics_low = tactics.get("lowest") if isinstance(tactics.get("lowest"), dict) else {}
    lessons_high = lessons.get("highest") if isinstance(lessons.get("highest"), dict) else {}
    rush_best = rush.get("best") if isinstance(rush.get("best"), dict) else {}
    rush_daily = rush.get("daily") if isinstance(rush.get("daily"), dict) else {}

    slim_games = []
    for game in games:
        slim = dict(game)
        slim.pop("pgn", None)
        slim_games.append(slim)

    return {
        "ok": True,
        "ready": True,
        "username": str(profile.get("username") or username),
        "name": str(profile.get("name") or ""),
        "title": str(profile.get("title") or ""),
        "country": country_code(profile),
        "joined": int(profile.get("joined") or 0),
        "lastOnline": int(profile.get("last_online") or 0),
        "followers": int(profile.get("followers") or 0),
        "league": str(profile.get("league") or ""),
        "fide": int(profile.get("fide") or 0),
        "timeClass": selected,
        "rating": selected_block["rating"],
        "bestRating": selected_block["best"],
        "record": selected_block["record"],
        "ratings": ratings,
        "tactics": {
            "highest": int(tactics_high.get("rating") or 0),
            "lowest": int(tactics_low.get("rating") or 0),
        },
        "lessons": {"highest": int(lessons_high.get("rating") or 0)},
        "puzzleRush": {
            "best": int(rush_best.get("score") or 0),
            "daily": int(rush_daily.get("score") or 0),
        },
        "games": slim_games,
        "packagesOk": not missing,
        "missingPackages": missing,
        "lastError": "",
    }


def load_lessons() -> dict[str, Any]:
    try:
        return json.loads(LESSONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"themes": {}, "ratingTracks": {}}


def lesson_url_ok(url: str) -> bool:
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return 200 <= int(resp.status) < 400
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405):
            try:
                get_req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
                with urllib.request.urlopen(get_req, timeout=12) as resp:
                    return 200 <= int(resp.status) < 400
            except (urllib.error.URLError, urllib.error.HTTPError):
                return exc.code != 404
        return False
    except urllib.error.URLError:
        return False


def collect_lesson_urls(catalog: dict[str, Any] | None = None) -> set[str]:
    data = catalog if catalog is not None else load_lessons()
    urls: set[str] = set()
    for theme in (data.get("themes") or {}).values():
        if not isinstance(theme, dict):
            continue
        for group in ("chesscom", "thirdParty"):
            for item in theme.get(group) or []:
                if isinstance(item, dict) and item.get("url"):
                    urls.add(str(item["url"]))
    for url in (data.get("ratingTracks") or {}).values():
        if url:
            urls.add(str(url))
    return urls


def verify_lesson_urls() -> tuple[list[str], list[str]]:
    alive: list[str] = []
    dead: list[str] = []
    for url in sorted(collect_lesson_urls()):
        if lesson_url_ok(url):
            alive.append(url)
        else:
            dead.append(url)
    return alive, dead


def filter_lessons(items: list[dict[str, Any]], allowed: set[str]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if url in allowed:
            out.append(item)
    return out


def phase_for_board(board: Any, ply: int) -> str:
    non_pawns = [piece for piece in board.piece_map().values() if piece.piece_type != 1]
    if len(non_pawns) <= 6:
        return "endgame"
    if ply <= 20:
        return "opening"
    return "middlegame"


def tag_move(board: Any, move: Any, best: Any, cpl: int, ply: int, user_color: Any) -> list[str]:
    import chess

    tags: list[str] = []
    phase = phase_for_board(board, ply)
    if phase == "opening":
        tags.append("opening")
    if phase == "endgame":
        tags.append("endgame")

    king_sq = board.king(user_color)
    uncastled = king_sq in (chess.E1, chess.E8) and board.has_castling_rights(user_color)
    if phase == "opening" and uncastled and ply >= 10:
        tags.append("king_safety")
        if best and board.is_castling(best) and not board.is_castling(move):
            tags.append("opening")

    if cpl >= MISTAKE_CP and best is not None:
        if board.is_capture(best) and not board.is_capture(move):
            tags.append("hanging_piece")
        if board.gives_check(best):
            tags.append("missed_tactic")
        piece = board.piece_at(best.from_square)
        if piece and piece.piece_type == chess.KNIGHT:
            tags.append("fork")
        if piece and piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            tags.append("pin")

    if cpl >= BLUNDER_CP and best is not None and board.gives_check(best):
        tags.append("checkmate")

    if not tags:
        tags.append("general")
    return list(dict.fromkeys(tags))


def classify_cpl(cpl: int) -> str:
    if cpl >= BLUNDER_CP:
        return "blunder"
    if cpl >= MISTAKE_CP:
        return "mistake"
    if cpl >= INACCURACY_CP:
        return "inaccuracy"
    return "ok"


def accuracy_from_cpls(cpls: list[int]) -> float:
    if not cpls:
        return 100.0
    scores = [max(0.0, min(100.0, 100.0 * math.exp(-min(cpl, 1000) / 250.0))) for cpl in cpls]
    return round(sum(scores) / len(scores), 1)


def score_cp(info: Any, color: Any) -> int:
    score = info.get("score") if isinstance(info, dict) else None
    if score is None:
        return 0
    pov = score.pov(color)
    value = pov.score(mate_score=10000)
    if value is None:
        return 0
    return int(value)


def analyze_game(game: dict[str, Any], username: str, depth: int) -> dict[str, Any]:
    missing = missing_packages()
    if missing:
        raise RuntimeError("Install with: omarchy pkg aur add " + " ".join(missing))

    import chess
    import chess.engine
    import chess.pgn
    import io

    pgn_text = str(game.get("pgn") or "")
    parsed = chess.pgn.read_game(io.StringIO(pgn_text))
    if parsed is None:
        raise RuntimeError("Could not parse the game PGN.")

    user_color = chess.WHITE if game.get("userColor") == "white" else chess.BLACK
    engine_path = stockfish_path()
    if not engine_path:
        raise RuntimeError("stockfish is not on PATH")

    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    board = parsed.board()
    errors: list[dict[str, Any]] = []
    cpls: list[int] = []
    counts = {"inaccuracy": 0, "mistake": 0, "blunder": 0, "ok": 0}
    phase_loss = {"opening": 0, "middlegame": 0, "endgame": 0}
    theme_loss: dict[str, int] = {}
    moves = list(parsed.mainline_moves())
    total_user = sum(1 for i, _ in enumerate(moves) if (i % 2 == 0) == (user_color == chess.WHITE))
    seen_user = 0

    try:
        engine.configure({"Threads": 1, "Hash": 64})
        for ply, move in enumerate(moves, start=1):
            is_user = board.turn == user_color
            if is_user:
                seen_user += 1
                eprint(f"Analyzing move {seen_user}/{max(total_user, 1)}…")
                info = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=1)
                if isinstance(info, list):
                    info = info[0]
                best = None
                pv = info.get("pv") or []
                if pv:
                    best = pv[0]
                before = score_cp(info, user_color)
                try:
                    san = board.san(move)
                except ValueError:
                    san = move.uci()
                best_san = ""
                if best is not None:
                    try:
                        best_san = board.san(best)
                    except ValueError:
                        best_san = best.uci()
                phase = phase_for_board(board, ply)
                tags = []
                board.push(move)
                after_info = engine.analyse(board, chess.engine.Limit(depth=depth))
                if isinstance(after_info, list):
                    after_info = after_info[0]
                after = score_cp(after_info, user_color)
                cpl = max(0, before - after)
                cpls.append(cpl)
                kind = classify_cpl(cpl)
                counts[kind] = counts.get(kind, 0) + 1
                phase_loss[phase] = phase_loss.get(phase, 0) + cpl
                board.pop()
                tags = tag_move(board, move, best, cpl, ply, user_color)
                for tag in tags:
                    theme_loss[tag] = theme_loss.get(tag, 0) + cpl
                if kind != "ok":
                    tip = move_tip(kind, san, best_san, cpl, tags, phase)
                    errors.append(
                        {
                            "ply": ply,
                            "moveNumber": (ply + 1) // 2,
                            "san": san,
                            "best": best_san,
                            "cpl": cpl,
                            "kind": kind,
                            "phase": phase,
                            "themes": tags,
                            "evalBefore": before,
                            "evalAfter": after,
                            "tip": tip,
                        }
                    )
                board.push(move)
            else:
                board.push(move)
    finally:
        engine.quit()

    errors.sort(key=lambda item: item["cpl"], reverse=True)
    ranked_themes = [name for name, _ in sorted(theme_loss.items(), key=lambda kv: kv[1], reverse=True) if name != "general"]
    if not ranked_themes:
        ranked_themes = ["general"]

    lessons = recommend_lessons(ranked_themes, int(game.get("whiteRating") if game.get("userColor") == "white" else game.get("blackRating") or 0))
    worst_phase = max(phase_loss, key=lambda key: phase_loss[key]) if any(phase_loss.values()) else "middlegame"

    return {
        "game": {k: v for k, v in game.items() if k != "pgn"},
        "username": username,
        "depth": depth,
        "accuracy": accuracy_from_cpls(cpls),
        "counts": counts,
        "phaseLoss": phase_loss,
        "worstPhase": worst_phase,
        "themes": ranked_themes,
        "errors": errors[:8],
        "tips": build_tips(errors, ranked_themes, worst_phase, counts),
        "lessons": lessons,
    }


def move_tip(kind: str, san: str, best_san: str, cpl: int, tags: list[str], phase: str) -> str:
    loss = f"{cpl} cp"
    better = f" Stockfish preferred {best_san}." if best_san and best_san != san else ""
    if "hanging_piece" in tags:
        return f"{san} dropped material ({loss}). Ask whether every piece is protected.{better}"
    if "checkmate" in tags:
        return f"{san} missed a forcing king attack ({loss}). Look for checks and mate threats first.{better}"
    if "king_safety" in tags:
        return f"{san} left the king in the center ({loss}). Castle before starting a fight.{better}"
    if "endgame" in tags:
        return f"{san} in the endgame lost {loss}. Activate the king and calculate the pawn race.{better}"
    if "opening" in tags:
        return f"{san} in the opening lost {loss}. Develop, take the center, then castle.{better}"
    if kind == "blunder":
        return f"{san} was a blunder ({loss}).{better}"
    if kind == "mistake":
        return f"{san} was a mistake ({loss}).{better}"
    return f"{san} was inaccurate ({loss}).{better}"


def build_tips(errors: list[dict[str, Any]], themes: list[str], worst_phase: str, counts: dict[str, int]) -> list[str]:
    tips: list[str] = []
    if counts.get("blunder", 0):
        tips.append(f"You had {counts['blunder']} blunder(s). Pause on every capture and check before you move.")
    if counts.get("mistake", 0) and not counts.get("blunder", 0):
        tips.append("Most of the damage was mistakes, not one-move blunders. Slow down at the critical moment.")
    if worst_phase == "opening":
        tips.append("The opening cost you the most. Develop pieces, castle, and only then hunt tactics.")
    elif worst_phase == "endgame":
        tips.append("The endgame cost you the most. Use the king, push passed pawns, and count before you trade.")
    else:
        tips.append("The middlegame swings were the problem. Before each move, scan hanging pieces and forced checks.")
    if "hanging_piece" in themes:
        tips.append("Look for unprotected pieces on every turn — yours and theirs.")
    if "king_safety" in themes:
        tips.append("If your king is still on e1/e8, castle before opening the center.")
    if not tips:
        tips.append("Clean game. Keep reviewing a few positions where the eval moved even a little.")
    return tips[:5]


def recommend_lessons(themes: list[str], rating: int) -> dict[str, list[dict[str, Any]]]:
    catalog = load_lessons()
    allowed = collect_lesson_urls(catalog)
    theme_map = catalog.get("themes") or {}
    chesscom: list[dict[str, Any]] = []
    third: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take(theme_name: str) -> None:
        block = theme_map.get(theme_name) or {}
        for item in filter_lessons(list(block.get("chesscom") or []), allowed):
            url = str(item.get("url") or "")
            if url in seen:
                continue
            seen.add(url)
            chesscom.append({"title": item.get("title"), "url": url, "source": "Chess.com", "kind": "lesson"})
        for item in filter_lessons(list(block.get("thirdParty") or []), allowed):
            url = str(item.get("url") or "")
            if url in seen:
                continue
            seen.add(url)
            third.append(
                {
                    "title": item.get("title"),
                    "url": url,
                    "source": item.get("source") or "Third-party",
                    "kind": item.get("kind") or "lesson",
                }
            )

    for theme in themes[:3]:
        take(theme)
    if not chesscom and not third:
        take("general")

    tracks = catalog.get("ratingTracks") or {}
    track_url = ""
    if rating and rating < 1000:
        track_url = str(tracks.get("beginner") or "")
    elif rating and rating < 1600:
        track_url = str(tracks.get("intermediate") or "")
    elif rating:
        track_url = str(tracks.get("advanced") or "")
    if track_url and track_url in allowed and track_url not in seen:
        label = "Beginner" if rating < 1000 else "Intermediate" if rating < 1600 else "Advanced"
        third.append(
            {
                "title": f"{label} chess lessons",
                "url": track_url,
                "source": "Saint Louis Chess Club",
                "kind": "curriculum",
            }
        )

    return {"chesscom": chesscom[:4], "thirdParty": third[:6]}


def fmt_eval(cp: int) -> str:
    if abs(cp) >= 9000:
        mate = max(1, (10000 - abs(cp)) // 10)
        sign = "#" if cp >= 0 else "#-"
        return f"{sign}{mate}"
    return f"{cp / 100:+.2f}"


def render_report(review: dict[str, Any]) -> str:
    game = review.get("game") or {}
    counts = review.get("counts") or {}
    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"
    red = "\033[31m"
    yellow = "\033[33m"
    cyan = "\033[36m"
    green = "\033[32m"

    kind_color = {"blunder": red, "mistake": yellow, "inaccuracy": cyan}

    lines = [
        f"{bold}OChessy game review{reset}",
        f"{dim}Local Stockfish depth {review.get('depth')} — not Chess.com Game Review{reset}",
        "",
        f"{bold}{game.get('white', '?')} vs {game.get('black', '?')}{reset}",
        f"{game.get('timeClass', '')} · you played {game.get('userColor', '')} · {game.get('result', '')}",
    ]
    if game.get("url"):
        lines.append(str(game["url"]))
    lines += [
        "",
        f"Estimated accuracy  {bold}{review.get('accuracy')}%{reset}",
        f"Inaccuracies {counts.get('inaccuracy', 0)}   Mistakes {counts.get('mistake', 0)}   Blunders {counts.get('blunder', 0)}",
        f"Biggest phase loss: {review.get('worstPhase')}",
        "",
        f"{bold}What to work on{reset}",
    ]
    for tip in review.get("tips") or []:
        lines.append(f"  • {tip}")

    errors = review.get("errors") or []
    if errors:
        lines += ["", f"{bold}Critical moments{reset}"]
        for err in errors[:5]:
            color = kind_color.get(err.get("kind"), "")
            lines.append(
                f"  {color}{err.get('kind', '').upper()}{reset}  "
                f"Move {err.get('moveNumber')}  {err.get('san')}  "
                f"({fmt_eval(err.get('evalBefore', 0))} → {fmt_eval(err.get('evalAfter', 0))}, -{err.get('cpl')} cp)"
            )
            lines.append(f"    {err.get('tip')}")

    lessons = review.get("lessons") or {}
    chesscom = lessons.get("chesscom") or []
    third = lessons.get("thirdParty") or []
    if chesscom:
        lines += ["", f"{bold}{green}Chess.com lessons{reset}"]
        for item in chesscom:
            lines.append(f"  • {item.get('title')}")
            lines.append(f"    {item.get('url')}")
    if third:
        lines += ["", f"{bold}{cyan}Third-party lessons{reset}{dim}  (not Chess.com){reset}"]
        for item in third:
            lines.append(f"  • {item.get('title')}  [{item.get('source')}]")
            lines.append(f"    {item.get('url')}")

    lines += ["", f"{dim}Press q to close.{reset}", ""]
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    try:
        payload = status_payload(username, args.time_class)
    except Exception as exc:  # noqa: BLE001 — surface API failures as JSON for the panel
        payload = {
            "ok": False,
            "ready": False,
            "username": username,
            "packagesOk": not missing_packages(),
            "missingPackages": missing_packages(),
            "lastError": str(exc),
            "games": [],
            "ratings": {},
            "record": {"win": 0, "loss": 0, "draw": 0},
        }
        print(json.dumps(payload))
        return 1
    print(json.dumps(payload))
    return 0 if payload.get("ok") else 1


def cmd_verify_lessons(_args: argparse.Namespace) -> int:
    alive, dead = verify_lesson_urls()
    for url in alive:
        print(f"OK   {url}")
    for url in dead:
        print(f"DEAD {url}")
    print(f"{len(alive)} ok, {len(dead)} dead")
    return 1 if dead else 0


def cmd_review(args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    if not username:
        eprint("Set a Chess.com username first.")
        return 2
    try:
        game = find_game(username, game_url=args.game_url or "", index=args.index)
        if not game.get("pgn"):
            raise RuntimeError("That game has no PGN in the public archive.")
        review = analyze_game(game, username, depth=max(8, min(18, int(args.depth))))
    except Exception as exc:  # noqa: BLE001
        eprint(str(exc))
        return 1
    text = render_report(review)
    if args.json:
        print(json.dumps(review, indent=2))
        return 0
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ochessy.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    status = sub.add_parser("status")
    status.add_argument("--username", default="")
    status.add_argument("--time-class", default="auto")
    status.set_defaults(func=cmd_status)

    review = sub.add_parser("review")
    review.add_argument("--username", required=True)
    review.add_argument("--time-class", default="auto")
    review.add_argument("--depth", type=int, default=12)
    review.add_argument("--game-url", default="")
    review.add_argument("--index", type=int, default=0)
    review.add_argument("--output", default="")
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=cmd_review)

    verify = sub.add_parser("verify-lessons")
    verify.set_defaults(func=cmd_verify_lessons)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
