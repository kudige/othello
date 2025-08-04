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
