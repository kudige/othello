import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.game import Game


def test_initial_valid_moves():
    game = Game()
    moves = set(game.valid_moves(1))
    expected = {(2, 3), (3, 2), (4, 5), (5, 4)}
    assert moves == expected


def test_move_flips_opponent():
    game = Game()
    assert game.make_move(2, 3, 1)
    # The move at (2,3) should flip one white at (3,3)
    assert game.board[2][3] == 1
    assert game.board[3][3] == 1
    black, white = game.score()
    assert black == 4 and white == 1
