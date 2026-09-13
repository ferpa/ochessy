# OChessy

Chess.com stats on the [Omarchy](https://omarchy.org/) bar, plus a local Stockfish review that opens in a terminal with tips and allowlisted lessons.

Chess.com’s public API does not expose Game Review (accuracy / blunders). OChessy downloads the PGN and classifies your moves with Stockfish, then recommends official Chess.com lessons and a small third-party allowlist (Lichess, Chess Tempo, Saint Louis Chess Club).

## Install

```bash
omarchy plugin add https://github.com/kingnickisverycool/ochessy.git --enable
```

From this folder (local development):

```bash
ln -sfn "$(pwd)" ~/.config/omarchy/plugins/ochessy
omarchy plugin validate "$(pwd)"
omarchy-shell shell rescanPlugins
omarchy plugin enable ochessy --section right
```

Saving files under `~/.config/omarchy/plugins/` reloads the plugin automatically.

## Dependencies

Bar stats use Chess.com’s public API (`https://api.chess.com/pub`). Game review is local: it downloads the PGN, then runs Stockfish.

On Omarchy, install the analyzer from the AUR:

```bash
omarchy pkg aur add stockfish python-chess
```

Ratings still work without those packages; review does not.

## First use

1. Left-click the bar pill
2. Enter your Chess.com username (or press `u`)
3. Left-click **Review last game**, or click a recent game

Review opens a terminal (`less`) with estimated accuracy, critical moments, Chess.com lessons, then third-party links labeled by publisher.

## Controls

- Left-click the bar pill to open stats
- Middle-click to review the last completed standard game
- Right-click to cycle the rating shown (`auto`, bullet, blitz, rapid, daily)
- Panel keys: `r` review, `s` refresh, `t` time class, `u` username, arrows / `j` `k` to move, Enter to activate

## Settings

Inline on the `ochessy` entry in `~/.config/omarchy/shell.json`:

```json
{
  "id": "ochessy",
  "username": "yourname",
  "timeClass": "auto",
  "depth": 12,
  "leelaSeconds": 0,
  "leelaPositions": 5,
  "moveTime": 0
}
```

The keys sit next to `"id"`, not inside a nested `settings` object:
`BarModel.entrySettings()` hands the widget every key of the layout entry except
`id`, so a nested object would arrive as a setting literally named `settings`
and the real keys would silently fall back to their defaults.

- `username` — Chess.com handle
- `timeClass` — `auto` uses the last played pool; otherwise `bullet`, `blitz`, `rapid`, or `daily`
- `depth` — Stockfish depth (8–18, default 12)
- `leelaSeconds` — seconds Leela spends per flagged position, `0` disables it (see below)
- `leelaPositions` — how many of the worst positions Leela revisits (0–8, default 5)
- `moveTime` — seconds per position instead of a fixed depth, `0` uses `depth` (0–5)

## What a review tells you

Every position in the game is analysed once, which costs the engine the same as
the old two-calls-per-played-move loop but yields three things instead of one:

**Your mistakes**, ranked by what they cost. Centipawn loss is measured on evals
clamped to ±1000, so a won game does not fill with phantom blunders: trading a
mate in 1 for a +16 endgame costs nothing, because it costs nothing.

**Chances you had.** Your opponent's mistakes are scored too, and the engine's
pick in the position right after each one is the punishment that was available.
Comparing it with what you actually played says whether you took it. In most
games this is the most actionable section — missed chances outnumber own
blunders.

**How the game swung**, as a one-row eval curve from your side of the board.

Reviews are cached under `~/.cache/ochessy/reviews/`, keyed by the game and by
the effort spent on it, so re-opening one is instant rather than a fresh
analysis. `--refresh` forces a re-run.

## Trends

```sh
python3 scripts/ochessy.py trends --username yourname
```

Reads the cached reviews and reports what holds across games rather than within
one: average accuracy and whether it is moving, blunders and missed chances per
game, the phase that keeps costing the most, and the themes that keep coming
back. The panel shows a short form of the same thing.

## Leela second opinion (optional)

Stockfish stays the primary engine and always does the full-game pass. When
`leelaSeconds` is greater than zero and [`lc0`](https://lczero.org/) is on
`PATH`, the worst positions Stockfish flagged are replayed through Leela and
the report gains a section comparing the two.

Only the flagged positions are revisited, never the whole game: Leela is a
neural engine and wants time or nodes rather than the fixed depth the Stockfish
pass uses, so a full-game run at comparable strength would take minutes. A time
limit is also the only limit that behaves the same on the CPU (openblas) and
CUDA builds.

The useful signal is the disagreement. When Leela likes a different move, or
rates the move you played far less harshly than Stockfish did, that position
was usually a real decision rather than a tactical oversight.

```sh
omarchy pkg aur add lc0        # pulls lc0-network, the weights, along with it
```

On hybrid graphics the engine has to be launched on the discrete GPU, so point
the plugin at a launcher instead of the bare binary:

```sh
export OCHESSY_LEELA_CMD="prime-run lc0"
```

If `lc0` is missing the review still runs; the report says so on one line and
the Stockfish analysis is unaffected.

## Lessons

Recommendations come from `scripts/lessons.json` only. Dead URLs are not guessed. Re-check the allowlist with:

```bash
python3 scripts/ochessy.py verify-lessons
```

## Removing

```bash
omarchy plugin disable ochessy
omarchy plugin remove ochessy
```

If you installed with a symlink, disable it, then remove `~/.config/omarchy/plugins/ochessy` yourself instead of `plugin remove`.
