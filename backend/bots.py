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


def minnie(game: Game, player: int, depth: int = 3) -> Optional[Tuple[int, int]]:
    """Minnie: minimax search using a positional weighting heuristic."""
    WEIGHTS = [
        [100, -20, 10, 5, 5, 10, -20, 100],
        [-20, -50, -2, -2, -2, -2, -50, -20],
        [10, -2, -1, -1, -1, -1, -2, 10],
        [5, -2, -1, -1, -1, -1, -2, 5],
        [5, -2, -1, -1, -1, -1, -2, 5],
        [10, -2, -1, -1, -1, -1, -2, 10],
        [-20, -50, -2, -2, -2, -2, -50, -20],
        [100, -20, 10, 5, 5, 10, -20, 100],
    ]

    def evaluate(g: Game) -> int:
        """Return weighted score from ``player``'s perspective."""
        score = 0
        for x in range(8):
            for y in range(8):
                score += WEIGHTS[x][y] * g.board[x][y]
        return score * player

    def minimax(g: Game, turn: int, d: int) -> int:
        moves = g.valid_moves(turn)
        if d == 0:
            return evaluate(g)
        if not moves:
            # Pass turn if opponent has moves; otherwise evaluate
            if g.valid_moves(-turn):
                return minimax(g, -turn, d - 1)
            return evaluate(g)
        if turn == player:
            best = -float("inf")
            for mx, my in moves:
                sim = copy.deepcopy(g)
                sim.make_move(mx, my, turn)
                best = max(best, minimax(sim, -turn, d - 1))
            return best
        else:
            best = float("inf")
            for mx, my in moves:
                sim = copy.deepcopy(g)
                sim.make_move(mx, my, turn)
                best = min(best, minimax(sim, -turn, d - 1))
            return best

    moves = game.valid_moves(player)
    if not moves:
        return None
    best_move = moves[0]
    best_val = -float("inf")
    for x, y in moves:
        sim = copy.deepcopy(game)
        sim.make_move(x, y, player)
        val = minimax(sim, -player, depth - 1)
        if val > best_val:
            best_val = val
            best_move = (x, y)
    return best_move


BOTS: dict[str, BotStrategy] = {
    "David": david,
    "Roger": roger,
    "Minnie": minnie,
}

