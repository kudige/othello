"""FastAPI WebSocket server for multiplayer Othello."""
from __future__ import annotations

import json
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .game import Game

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory store of games and connections
class ConnectionManager:
    def __init__(self) -> None:
        self.active: Dict[str, List[WebSocket]] = {}
        self.games: Dict[str, Game] = {}

    async def connect(self, game_id: str, websocket: WebSocket) -> str:
        await websocket.accept()
        if game_id not in self.active:
            self.active[game_id] = []
            self.games[game_id] = Game()
        players = self.active[game_id]
        players.append(websocket)
        return "black" if len(players) == 1 else "white"

    def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        players = self.active.get(game_id)
        if players and websocket in players:
            players.remove(websocket)
        if not players:
            self.active.pop(game_id, None)
            self.games.pop(game_id, None)

    async def broadcast(self, game_id: str, message: dict) -> None:
        for connection in self.active.get(game_id, []):
            await connection.send_text(json.dumps(message))


manager = ConnectionManager()


@app.get("/")
async def get_index() -> HTMLResponse:
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    color = await manager.connect(game_id, websocket)
    game = manager.games[game_id]
    await websocket.send_text(json.dumps({"type": "init", "board": game.board, "color": color, "current": game.current_player}))
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "move":
                x, y = msg["x"], msg["y"]
                player = 1 if msg["color"] == "black" else -1
                if game.current_player == player and game.make_move(x, y, player):
                    await manager.broadcast(game_id, {"type": "update", "board": game.board, "current": game.current_player})
                else:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid move"}))
    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

