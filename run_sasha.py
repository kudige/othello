#!/usr/bin/env python3
"""Run the Sasha bot on a saved game file."""
import argparse
import json
from pathlib import Path

from backend.game import Game
from backend.bots import sasha


def load_game(path: Path) -> Game:
    """Load a saved game state from ``path``.

    The file may either contain a single game state or a history list as
    produced by the web client. In the latter case the last state in the
    history is used.
    """
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, dict) and "history" in data:
        state = data["history"][-1]
    else:
        state = data
    game = Game()
    game.board = state["board"]
    game.current_player = state["current"]
    last = state.get("last")
    game.last_move = tuple(last) if last is not None else None
    return game


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sasha bot on a saved game")
    parser.add_argument("file", type=Path, help="Path to saved game JSON file")
    parser.add_argument(
        "--verbose", action="store_true", help="Print Sasha's thinking process"
    )
    args = parser.parse_args()

    game = load_game(args.file)
    move = sasha(game, game.current_player, verbose=args.verbose)
    if move:
        print(f"Next move: {move[0]} {move[1]}")
    else:
        print("No valid moves available.")


if __name__ == "__main__":
    main()
