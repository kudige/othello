"""FastAPI WebSocket server for multiplayer Othello."""
from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional

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
        self._counter = 1

    def create_game(self) -> str:
        """Create a new empty game and return its id."""
        game_id = str(self._counter)
        self._counter += 1
        self.active[game_id] = {"black": None, "white": None}
        self.games[game_id] = Game()
        self.names[game_id] = {"black": "", "white": ""}
        self.release_tasks[game_id] = {"black": None, "white": None}
        self.room_names[game_id] = f"Game {game_id}"
        return game_id

    async def connect(self, game_id: str, websocket: WebSocket, name: Optional[str] = None) -> str:
        await websocket.accept()
        if game_id not in self.active:
            # Auto-create if missing (e.g., manual room creation)
            self.active[game_id] = {"black": None, "white": None}
            self.games[game_id] = Game()
            self.names[game_id] = {"black": "", "white": ""}
            self.release_tasks[game_id] = {"black": None, "white": None}
            self.room_names.setdefault(game_id, f"Game {game_id}")
        players = self.active[game_id]
        names = self.names[game_id]
        # Try to assign color based on stored name first
        if name and names.get("black") == name:
            color = "black"
        elif name and names.get("white") == name:
            color = "white"
        elif players["black"] is None and names["black"] == "":
            color = "black"
        elif players["white"] is None and names["white"] == "":
            color = "white"
        else:
            # Both spots taken or seat reserved
            await websocket.close()
            raise WebSocketDisconnect()
        players[color] = websocket
        # Cancel any pending release task for this seat
        task = self.release_tasks.get(game_id, {}).get(color)
        if task:
            task.cancel()
            self.release_tasks[game_id][color] = None
        return color

    def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        players = self.active.get(game_id)
        if not players:
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
        finally:
            # Clear reference to the completed task
            if game_id in self.release_tasks:
                self.release_tasks[game_id][color] = None

    async def broadcast(self, game_id: str, message: dict) -> None:
        for connection in self.active.get(game_id, {}).values():
            if connection:
                await connection.send_text(json.dumps(message))


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


@app.get("/create")
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
            if msg.get("action") == "move":
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
            elif msg.get("action") == "name":
                # Store the player's name and inform all connected clients.
                manager.names[game_id][color] = msg.get("name", "")
                await manager.broadcast(
                    game_id,
                    {
                        "type": "players",
                        "players": manager.names[game_id],
                        "current": game.current_player,
                    },
                )
    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

