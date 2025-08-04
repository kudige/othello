"""FastAPI WebSocket server for multiplayer Othello."""
from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .game import Game

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


# In-memory store of games and connections
class ConnectionManager:
    def __init__(self) -> None:
        # Active connections per game keyed by color.
        self.active: Dict[str, Dict[str, Optional[WebSocket]]] = {}
        self.games: Dict[str, Game] = {}
        # Track player names per game. Keys are game ids and values are
        # dictionaries mapping color ("black"/"white") to the player's name.
        self.names: Dict[str, Dict[str, str]] = {}
        # Track pending tasks that release a reserved seat after a delay.
        self.release_tasks: Dict[str, Dict[str, Optional[asyncio.Task]]] = {}
        # Human friendly room names
        self.room_names: Dict[str, str] = {}
        # Connections that are merely spectating a given game.
        self.watchers: Dict[str, Set[WebSocket]] = {}
        self._counter = 1

    def create_game(self) -> str:
        """Create a new empty game and return its id."""
        game_id = str(self._counter)
        self._counter += 1
        self.active[game_id] = {"black": None, "white": None}
        self.games[game_id] = Game()
        self.names[game_id] = {"black": "", "white": ""}
        self.release_tasks[game_id] = {"black": None, "white": None}
        self.watchers[game_id] = set()
        self.room_names[game_id] = f"Game {game_id}"
        return game_id

    async def connect(self, game_id: str, websocket: WebSocket, name: Optional[str] = None) -> Optional[str]:
        """Accept a websocket connection.

        By default players join as spectators. If a seat with the given
        ``name`` is reserved and currently empty, they automatically reclaim it.
        """
        await websocket.accept()
        if game_id not in self.active:
            # Auto-create if missing (e.g., manual room creation)
            self.active[game_id] = {"black": None, "white": None}
            self.games[game_id] = Game()
            self.names[game_id] = {"black": "", "white": ""}
            self.release_tasks[game_id] = {"black": None, "white": None}
            self.watchers[game_id] = set()
            self.room_names.setdefault(game_id, f"Game {game_id}")
        players = self.active[game_id]
        names = self.names[game_id]

        color: Optional[str] = None
        if name and names.get("black") == name and players["black"] is None:
            color = "black"
        elif name and names.get("white") == name and players["white"] is None:
            color = "white"

        if color:
            players[color] = websocket
            # Cancel any pending release task for this seat
            task = self.release_tasks.get(game_id, {}).get(color)
            if task:
                task.cancel()
                self.release_tasks[game_id][color] = None
        else:
            # Join as spectator
            self.watchers.setdefault(game_id, set()).add(websocket)
        return color

    def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        players = self.active.get(game_id)
        if not players:
            return
        # Remove from spectator list if present
        watchers = self.watchers.get(game_id, set())
        if websocket in watchers:
            watchers.discard(websocket)
            return
        for color, ws in players.items():
            if ws is websocket:
                players[color] = None
                # Schedule seat release after 60 seconds
                existing = self.release_tasks.setdefault(game_id, {}).get(color)
                if existing:
                    existing.cancel()
                self.release_tasks[game_id][color] = asyncio.create_task(
                    self._release_seat(game_id, color)
                )

    async def _release_seat(self, game_id: str, color: str) -> None:
        try:
            await asyncio.sleep(60)
            players = self.active.get(game_id)
            if players and players[color] is None:
                # Seat becomes available to anyone
                self.names[game_id][color] = ""
                # Notify remaining players that the seat is open so the UI
                # updates without requiring a refresh. We include the current
                # player so the client can keep rendering turn indicators.
                game = self.games.get(game_id)
                await self.broadcast(
                    game_id,
                    {
                        "type": "players",
                        "players": self.names[game_id],
                        "current": game.current_player if game else 0,
                    },
                )
        finally:
            # Clear reference to the completed task
            if game_id in self.release_tasks:
                self.release_tasks[game_id][color] = None

    async def broadcast(self, game_id: str, message: dict) -> None:
        # Send to seated players
        for connection in self.active.get(game_id, {}).values():
            if connection:
                await connection.send_text(json.dumps(message))
        # And to any spectators
        for ws in self.watchers.get(game_id, set()):
            await ws.send_text(json.dumps(message))

    def claim_seat(self, game_id: str, websocket: WebSocket, color: str, name: str) -> bool:
        """Attempt to assign ``websocket`` the requested seat."""
        players = self.active.get(game_id)
        names = self.names.get(game_id)
        if not players or not names:
            return False
        if players[color] is None and (names[color] in ("", name)):
            players[color] = websocket
            names[color] = name
            self.watchers.get(game_id, set()).discard(websocket)
            # Cancel any pending release task
            task = self.release_tasks.get(game_id, {}).get(color)
            if task:
                task.cancel()
                self.release_tasks[game_id][color] = None
            return True
        return False


manager = ConnectionManager()


@app.get("/")
async def get_lobby() -> HTMLResponse:
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/game/{game_id}")
async def get_game(game_id: str) -> HTMLResponse:
    with open("static/game.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/rooms")
async def list_rooms() -> dict:
    return {
        "rooms": [
            {"id": gid, "name": manager.room_names.get(gid, gid), "players": manager.names[gid]}
            for gid in manager.games.keys()
        ]
    }


@app.post("/create")
async def create_room() -> dict:
    gid = manager.create_game()
    return {"id": gid, "name": manager.room_names[gid]}


@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    name = websocket.query_params.get("name")
    color = await manager.connect(game_id, websocket, name)
    game = manager.games[game_id]
    await websocket.send_text(
        json.dumps(
            {
                "type": "init",
                "board": game.board,
                "color": color,
                "current": game.current_player,
                "players": manager.names[game_id],
            }
        )
    )
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")
            if action == "move":
                x, y = msg["x"], msg["y"]
                player = 1 if msg["color"] == "black" else -1
                if game.current_player == player and game.make_move(x, y, player):
                    await manager.broadcast(
                        game_id,
                        {
                            "type": "update",
                            "board": game.board,
                            "current": game.current_player,
                            "players": manager.names[game_id],
                        },
                    )
                else:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid move"}))
            elif action == "name":
                # Store the player's name and inform all connected clients.
                if color:
                    manager.names[game_id][color] = msg.get("name", "")
                    await manager.broadcast(
                        game_id,
                        {
                            "type": "players",
                            "players": manager.names[game_id],
                            "current": game.current_player,
                        },
                    )
            elif action == "sit":
                requested = msg.get("color")
                desired_name = msg.get("name", "")
                if manager.claim_seat(game_id, websocket, requested, desired_name):
                    color = requested
                    await websocket.send_text(json.dumps({"type": "seat", "color": color}))
                    await manager.broadcast(
                        game_id,
                        {
                            "type": "players",
                            "players": manager.names[game_id],
                            "current": game.current_player,
                        },
                    )
                else:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Seat taken"}))
    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

