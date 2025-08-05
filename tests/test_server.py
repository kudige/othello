import asyncio
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from backend.server import ConnectionManager, app
from backend.game import Game


class DummyWebSocket:
    async def accept(self):
        pass

    async def close(self):
        pass


def test_seat_reserved_and_released(monkeypatch):
    async def run_test():
        manager = ConnectionManager()
        gid = manager.create_game()

        # Replace _release_seat with controllable version
        release_event = asyncio.Event()

        async def fake_release(game_id, color):
            await release_event.wait()
            players = manager.active.get(game_id)
            if players and players[color] is None:
                manager.names[game_id][color] = ""
            manager.release_tasks[game_id][color] = None

        monkeypatch.setattr(manager, "_release_seat", fake_release)

        ws1 = DummyWebSocket()
        await manager.connect(gid, ws1, name="alice")
        assert manager.claim_seat(gid, ws1, "black", "alice")
        manager.disconnect(gid, ws1)

        # Another player connects while seat is reserved.
        ws2 = DummyWebSocket()
        await manager.connect(gid, ws2, name="bob")
        assert not manager.claim_seat(gid, ws2, "black", "bob")
        assert manager.claim_seat(gid, ws2, "white", "bob")
        # Reserved seat is still empty and retains original name.
        assert manager.active[gid]["black"] is None
        assert manager.names[gid]["black"] == "alice"

        # After releasing the seat, a new player may take it
        release_event.set()
        await asyncio.sleep(0)
        ws3 = DummyWebSocket()
        await manager.connect(gid, ws3, name="carol")
        assert manager.claim_seat(gid, ws3, "black", "carol")

    asyncio.run(run_test())


def test_create_room_endpoint_rejects_get_and_returns_unique_ids():
    client = TestClient(app)

    first = client.post("/create")
    second = client.post("/create")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]

    disallowed = client.get("/create")
    assert disallowed.status_code == 405


def test_release_notifies_clients(monkeypatch):
    async def run_test():
        monkeypatch.setattr(
            ConnectionManager, "_schedule_room_cleanup", lambda self, game_id: None
        )
        manager = ConnectionManager()
        gid = manager.create_game()

        ws = DummyWebSocket()
        await manager.connect(gid, ws, name="alice")
        assert manager.claim_seat(gid, ws, "black", "alice")

        # Capture broadcast messages
        messages = []

        async def fake_broadcast(game_id, message):
            messages.append((game_id, message))

        monkeypatch.setattr(manager, "broadcast", fake_broadcast)

        # Speed up the release task by replacing asyncio.sleep
        real_sleep = asyncio.sleep

        async def fast_sleep(_):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        manager.disconnect(gid, ws)

        # Wait for the release task to complete
        await manager.release_tasks[gid]["black"]

        assert manager.names[gid]["black"] == ""
        assert messages and messages[0][1]["type"] == "players"
        assert messages[0][1]["players"]["black"] == ""

    asyncio.run(run_test())


def test_room_removed_when_missing_player(monkeypatch):
    async def run_test():
        manager = ConnectionManager()
        gid = manager.create_game()

        ws1 = DummyWebSocket()
        await manager.connect(gid, ws1, name="alice")
        assert manager.claim_seat(gid, ws1, "black", "alice")

        ws2 = DummyWebSocket()
        await manager.connect(gid, ws2, name="bob")
        assert manager.claim_seat(gid, ws2, "white", "bob")

        async def noop_broadcast(game_id, message):
            pass

        monkeypatch.setattr(manager, "broadcast", noop_broadcast)

        real_sleep = asyncio.sleep

        async def fast_sleep(_):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        manager.disconnect(gid, ws1)

        task = manager.cleanup_tasks[gid]
        await task

        assert gid not in manager.games

    asyncio.run(run_test())


def test_room_removed_when_empty(monkeypatch):
    async def run_test():
        manager = ConnectionManager()
        gid = manager.create_game()

        async def noop_broadcast(game_id, message):
            pass

        monkeypatch.setattr(manager, "broadcast", noop_broadcast)

        real_sleep = asyncio.sleep

        async def fast_sleep(_):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        task = manager.cleanup_tasks[gid]
        await task

        assert gid not in manager.games

    asyncio.run(run_test())


def test_bot_moves(monkeypatch):
    async def run_test():
        manager = ConnectionManager()
        gid = manager.create_game()

        # Capture broadcast messages
        messages = []

        async def fake_broadcast(game_id, message):
            messages.append(message)

        monkeypatch.setattr(manager, "broadcast", fake_broadcast)

        # Seat a bot as white and let it move (white starts)
        assert manager.add_bot(gid, "white")
        await manager.bot_move(gid)

        game = manager.games[gid]
        # Bot should play a valid move and switch to black's turn
        assert game.board[2][4] == -1
        assert game.current_player == 1
        assert messages and messages[0]["type"] == "update"

    asyncio.run(run_test())


def test_restart_game_resets_board(monkeypatch):
    monkeypatch.setattr(
        ConnectionManager, "_schedule_room_cleanup", lambda self, gid: None
    )
    manager = ConnectionManager()
    gid = manager.create_game()
    game = manager.games[gid]
    game.board[0][0] = 1
    game.current_player = 0
    assert manager.restart_game(gid)
    new_game = manager.games[gid]
    assert new_game.current_player == -1
    assert new_game.board == Game().board
