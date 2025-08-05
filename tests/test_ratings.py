from backend.server import ConnectionManager


def test_ratings_persist_across_instances(tmp_path, monkeypatch):
    ratings_file = tmp_path / "ratings.json"
    monkeypatch.setattr(
        ConnectionManager, "_schedule_room_cleanup", lambda self, gid: None
    )
    manager = ConnectionManager(ratings_path=ratings_file)
    gid = manager.create_game()
    manager.names[gid]["black"] = "alice"
    manager.names[gid]["white"] = "bob"
    game = manager.games[gid]
    game.board[0][0] = 1  # give black an extra disc
    manager.update_ratings(gid)
    alice = manager.get_rating("alice")
    bob = manager.get_rating("bob")
    # Ensure ratings were updated
    assert alice != 1500 and bob != 1500
    # New manager should load saved ratings
    new_manager = ConnectionManager(ratings_path=ratings_file)
    assert new_manager.get_rating("alice") == alice
    assert new_manager.get_rating("bob") == bob
