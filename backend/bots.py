"""Bot strategies for Othello."""
from __future__ import annotations

from typing import Callable, Optional, Tuple
from functools import partial

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
        sim = game.copy()
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
                sim = g.copy()
                sim.make_move(mx, my, turn)
                best = max(best, minimax(sim, -turn, d - 1))
            return best
        else:
            best = float("inf")
            for mx, my in moves:
                sim = g.copy()
                sim.make_move(mx, my, turn)
                best = min(best, minimax(sim, -turn, d - 1))
            return best

    moves = game.valid_moves(player)
    if not moves:
        return None
    best_move = moves[0]
    best_val = -float("inf")
    for x, y in moves:
        sim = game.copy()
        sim.make_move(x, y, player)
        val = minimax(sim, -player, depth - 1)
        if val > best_val:
            best_val = val
            best_move = (x, y)
    return best_move


def sasha(game: Game, player: int, max_depth: int = 6) -> Optional[Tuple[int, int]]:
    """Sasha: a stronger bot using minimax with alpha-beta pruning.

    The strategy includes a heuristic evaluation function, move ordering,
    a tiny opening book, iterative deepening, a transposition table and an
    endgame solver that searches to the end when few squares remain.
    """

    # --- Opening book ---------------------------------------------------
    total_pieces = sum(abs(cell) for row in game.board for cell in row)
    if total_pieces == 4:  # initial position
        if player == -1:
            return (2, 4)  # classic opening move for white
        return (2, 3)  # answer for black

    opponent = -player

    corners = {(0, 0), (0, 7), (7, 0), (7, 7)}
    bad_squares = {
        (0, 1), (1, 0), (1, 1),
        (0, 6), (1, 7), (1, 6),
        (6, 0), (7, 1), (6, 1),
        (6, 6), (6, 7), (7, 6),
    }

    def evaluate(g: Game) -> int:
        """Heuristic evaluation of ``g`` from ``player``'s perspective."""

        player_count = opponent_count = 0
        player_corners = opponent_corners = 0
        player_edges = opponent_edges = 0
        player_bad = opponent_bad = 0
        for x in range(8):
            for y in range(8):
                cell = g.board[x][y]
                if cell == 0:
                    continue
                if cell == player:
                    player_count += 1
                    if (x, y) in corners:
                        player_corners += 1
                    elif x == 0 or x == 7 or y == 0 or y == 7:
                        player_edges += 1
                    if (x, y) in bad_squares:
                        player_bad += 1
                else:
                    opponent_count += 1
                    if (x, y) in corners:
                        opponent_corners += 1
                    elif x == 0 or x == 7 or y == 0 or y == 7:
                        opponent_edges += 1
                    if (x, y) in bad_squares:
                        opponent_bad += 1

        # Mobility
        player_moves = len(g.valid_moves(player))
        opponent_moves = len(g.valid_moves(opponent))

        # Game phase adjustment
        pieces = player_count + opponent_count
        if pieces <= 20:
            disk_w, mob_w, corner_w, edge_w, bad_w = 10, 80, 800, 40, 60
        elif pieces <= 52:
            disk_w, mob_w, corner_w, edge_w, bad_w = 30, 60, 800, 60, 40
        else:
            disk_w, mob_w, corner_w, edge_w, bad_w = 100, 20, 800, 20, 0

        score = 0
        score += disk_w * (player_count - opponent_count)
        score += mob_w * (player_moves - opponent_moves)
        score += corner_w * (player_corners - opponent_corners)
        score += edge_w * (player_edges - opponent_edges)
        score -= bad_w * (player_bad - opponent_bad)
        return score

    def order_moves(g: Game, moves: list[Tuple[int, int]], turn: int) -> list[Tuple[int, int]]:
        def key(m: Tuple[int, int]) -> tuple[int, int]:
            x, y = m
            if (x, y) in corners:
                return (0, 0)
            if (x, y) in bad_squares:
                return (3, 0)
            priority = 1 if (x == 0 or x == 7 or y == 0 or y == 7) else 2
            flips = -len(g._captures(x, y, turn))
            return (priority, flips)

        return sorted(moves, key=key)

    trans_table: dict[tuple, int] = {}

    def alphabeta(g: Game, depth: int, alpha: int, beta: int, turn: int) -> int:
        key = (tuple(tuple(r) for r in g.board), turn, depth)
        if key in trans_table:
            return trans_table[key]

        moves = g.valid_moves(turn)
        if depth == 0 or (not moves and not g.valid_moves(-turn)):
            val = evaluate(g)
            trans_table[key] = val
            return val
        if not moves:
            val = alphabeta(g, depth - 1, alpha, beta, -turn)
            trans_table[key] = val
            return val

        if turn == player:
            value = -float("inf")
            for mx, my in order_moves(g, moves, turn):
                sim = g.copy()
                sim.make_move(mx, my, turn)
                value = max(value, alphabeta(sim, depth - 1, alpha, beta, -turn))
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
        else:
            value = float("inf")
            for mx, my in order_moves(g, moves, turn):
                sim = g.copy()
                sim.make_move(mx, my, turn)
                value = min(value, alphabeta(sim, depth - 1, alpha, beta, -turn))
                beta = min(beta, value)
                if alpha >= beta:
                    break
        trans_table[key] = value
        return value

    moves = game.valid_moves(player)
    if not moves:
        return None

    empties = 64 - total_pieces
    if empties <= 12:
        max_depth = empties  # search to the endgame

    best_move = moves[0]
    for depth in range(1, max_depth + 1):  # iterative deepening
        best_val = -float("inf")
        for x, y in order_moves(game, moves, player):
            sim = game.copy()
            sim.make_move(x, y, player)
            val = alphabeta(sim, depth - 1, -float("inf"), float("inf"), -player)
            if val > best_val:
                best_val = val
                best_move = (x, y)
    return best_move


BOTS: dict[str, BotStrategy] = {
    "David": david,
    "Roger": roger,
    "Minnie": minnie,
    "Sasha senior": sasha,
    "Sasha junior": partial(sasha, max_depth=5),
    "Sasha intern": partial(sasha, max_depth=4),
}

