"""Bot strategies for Othello."""
from __future__ import annotations

from typing import Callable, Optional, Tuple
import copy

from .game import Game

BotStrategy = Callable[[Game, int], Optional[Tuple[int, int]]]


def david(game: Game, player: int) -> Optional[Tuple[int, int]]:
    """David: choose the move that flips the most discs."""
    return game.best_move(player)


def roger(game: Game, player: int) -> Optional[Tuple[int, int]]:
    """Roger: choose move giving opponent the fewest options next turn."""
    moves = game.valid_moves(player)
    if not moves:
        return None
    best_move = moves[0]
    min_opponent = float("inf")
    for x, y in moves:
        sim = copy.deepcopy(game)
        sim.make_move(x, y, player)
        opp_moves = len(sim.valid_moves(-player))
        if opp_moves < min_opponent:
            min_opponent = opp_moves
            best_move = (x, y)
    return best_move


BOTS: dict[str, BotStrategy] = {
    "David": david,
    "Roger": roger,
}

