import asyncio
import pytest
from fastapi import WebSocketDisconnect

from backend.server import ConnectionManager


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
        color = await manager.connect(gid, ws1, name="alice")
        manager.names[gid][color] = "alice"
        manager.disconnect(gid, ws1)

        # Another player connects while seat is reserved.
        ws2 = DummyWebSocket()
        color_bob = await manager.connect(gid, ws2, name="bob")
        assert color_bob != color
        # Reserved seat is still empty and retains original name.
        assert manager.active[gid][color] is None
        assert manager.names[gid][color] == "alice"

        # After releasing the seat, a new player may take it
        release_event.set()
        await asyncio.sleep(0)
        ws3 = DummyWebSocket()
        color2 = await manager.connect(gid, ws3, name="carol")
        assert color2 == color

    asyncio.run(run_test())


def test_release_notifies_clients(monkeypatch):
    async def run_test():
        manager = ConnectionManager()
        gid = manager.create_game()

        ws = DummyWebSocket()
        color = await manager.connect(gid, ws, name="alice")
        manager.names[gid][color] = "alice"

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
        await manager.release_tasks[gid][color]

        assert manager.names[gid][color] == ""
        assert messages and messages[0][1]["type"] == "players"
        assert messages[0][1]["players"][color] == ""

    asyncio.run(run_test())
