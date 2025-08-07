"""Othello game logic."""
from __future__ import annotations

from typing import List, Tuple, Optional

BOARD_SIZE = 8


class Game:
    """Simple Othello game state."""

    def __init__(self) -> None:
        # Board represented as 2D list: 0 empty, 1 black, -1 white
        self.board: List[List[int]] = [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        mid = BOARD_SIZE // 2
        # Starting pieces
        self.board[mid - 1][mid - 1] = -1
        self.board[mid][mid] = -1
        self.board[mid - 1][mid] = 1
        self.board[mid][mid - 1] = 1
        self.current_player = -1  # white starts
        # Track the coordinates of the most recent move. ``None`` means no
        # moves have been played yet.
        self.last_move: Optional[Tuple[int, int]] = None

    def copy(self) -> "Game":
        """Return a deep copy of the current game state.

        The game object is small and consists primarily of primitive data
        structures, so duplicating it manually is significantly faster than
        using ``copy.deepcopy`` for the thousands of copies performed during
        bot search.
        """

        # Bypass ``__init__`` to avoid re-creating the initial board only to
        # overwrite it immediately.
        new_game = Game.__new__(Game)
        new_game.board = [row[:] for row in self.board]
        new_game.current_player = self.current_player
        new_game.last_move = self.last_move
        return new_game

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE

    def valid_moves(self, player: Optional[int] = None) -> List[Tuple[int, int]]:
        if player is None:
            player = self.current_player
        moves = []
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                if self.board[x][y] == 0 and self._captures(x, y, player):
                    moves.append((x, y))
        return moves

    def _captures(self, x: int, y: int, player: int) -> List[Tuple[int, int]]:
        opponent = -player
        captured = []
        # Directions: 8 surrounding directions
        directions = [
            (-1, -1), (0, -1), (1, -1),
            (-1, 0),          (1, 0),
            (-1, 1),  (0, 1), (1, 1),
        ]
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            temp = []
            while self.inside(nx, ny) and self.board[nx][ny] == opponent:
                temp.append((nx, ny))
                nx += dx
                ny += dy
            if self.inside(nx, ny) and self.board[nx][ny] == player and temp:
                captured.extend(temp)
        return captured

    def make_move(self, x: int, y: int, player: Optional[int] = None) -> bool:
        """Place a piece for player at x,y. Returns True if move valid."""
        if player is None:
            player = self.current_player
        if not self.inside(x, y) or self.board[x][y] != 0:
            return False
        captured = self._captures(x, y, player)
        if not captured:
            return False
        self.board[x][y] = player
        # Record the move before flipping captured discs. This information is
        # surfaced to clients so they can highlight the last move played on the
        # board.
        self.last_move = (x, y)
        for cx, cy in captured:
            self.board[cx][cy] = player
        self.current_player = -player
        # If opponent has no moves, stay on current player
        if not self.valid_moves(self.current_player):
            self.current_player = player
            if not self.valid_moves(self.current_player):
                self.current_player = 0  # game over
        return True

    def score(self) -> Tuple[int, int]:
        black = sum(cell == 1 for row in self.board for cell in row)
        white = sum(cell == -1 for row in self.board for cell in row)
        return black, white

    def best_move(self, player: Optional[int] = None) -> Optional[Tuple[int, int]]:
        """Return the move that captures the most discs for ``player``.

        If no moves are available, ``None`` is returned. A very small
        heuristic is used: simply choose the move that flips the maximum
        number of opponent discs. When several moves tie, the first one in
        scan order is selected.
        """
        if player is None:
            player = self.current_player
        moves = self.valid_moves(player)
        if not moves:
            return None
        return max(moves, key=lambda m: len(self._captures(m[0], m[1], player)))

