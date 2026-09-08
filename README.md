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
  "depth": 12
}
```

- `username` — Chess.com handle
- `timeClass` — `auto` uses the last played pool; otherwise `bullet`, `blitz`, `rapid`, or `daily`
- `depth` — Stockfish depth (8–18, default 12)

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
