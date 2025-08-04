"""FastAPI WebSocket server for multiplayer Othello."""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .game import Game

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory store of games and connections
class ConnectionManager:
    def __init__(self) -> None:
        # Track active connections per game. For each game we store the
        # websocket for the black and white player as well as any spectators.
        self.active: Dict[str, Dict[str, object]] = {}
        self.games: Dict[str, Game] = {}
        # Track player names per game. Keys are game ids and values are
        # dictionaries mapping color ("black"/"white") to the player's name.
        self.names: Dict[str, Dict[str, str]] = {}
        # Incremental id counter for friendly game names.
        self.counter: int = 0

    def _init_game(self, game_id: str) -> None:
        """Initialize data structures for a new game if it doesn't exist."""
        if game_id not in self.active:
            self.active[game_id] = {"black": None, "white": None, "spectators": []}
            self.games[game_id] = Game()
            self.names[game_id] = {"black": "", "white": ""}

    def create_game(self) -> str:
        """Create a new game and return its id."""
        self.counter += 1
        game_id = str(self.counter)
        self._init_game(game_id)
        return game_id

    async def connect(self, game_id: str, websocket: WebSocket, requested: Optional[str] = None) -> str:
        await websocket.accept()
        self._init_game(game_id)
        players = self.active[game_id]

        # If the client requested a specific color and that slot is free, honor it.
        if requested in ("black", "white") and players[requested] is None:
            players[requested] = websocket
            return requested

        if players["black"] is None:
            players["black"] = websocket
            return "black"
        if players["white"] is None:
            players["white"] = websocket
            return "white"

        players["spectators"].append(websocket)
        return "spectator"

    def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        players = self.active.get(game_id)
        if not players:
            return
        if players.get("black") is websocket:
            players["black"] = None
        elif players.get("white") is websocket:
            players["white"] = None
        elif websocket in players.get("spectators", []):
            players["spectators"].remove(websocket)

    async def broadcast(self, game_id: str, message: dict) -> None:
        players = self.active.get(game_id, {})
        connections: List[WebSocket] = []
        for key in ("black", "white"):
            ws = players.get(key)
            if ws is not None:
                connections.append(ws)
        connections.extend(players.get("spectators", []))
        for connection in connections:
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
            {"id": gid, "name": f"Game {gid}", "players": players}
            for gid, players in manager.names.items()
        ]
    }


@app.post("/create")
async def create_room() -> dict:
    new_id = manager.create_game()
    return {"id": new_id}


@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    requested = websocket.query_params.get("color")
    color = await manager.connect(game_id, websocket, requested)
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
            elif msg.get("action") == "name" and color in ("black", "white"):
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

