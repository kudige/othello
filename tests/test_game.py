import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.game import Game


def test_initial_valid_moves():
    game = Game()
    moves = set(game.valid_moves(-1))
    expected = {(2, 4), (3, 5), (4, 2), (5, 3)}
    assert moves == expected


def test_move_flips_opponent():
    game = Game()
    assert game.make_move(2, 4, -1)
    # The move at (2,4) should flip one black at (3,4)
    assert game.board[2][4] == -1
    assert game.board[3][4] == -1
    black, white = game.score()
    assert black == 1 and white == 4


def test_last_move_tracking():
    game = Game()
    assert game.last_move is None
    assert game.make_move(2, 4, -1)
    assert game.last_move == (2, 4)
