"""FastAPI WebSocket server for multiplayer Othello."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .game import Game
from .bots import BOTS

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


# In-memory store of games and connections
class ConnectionManager:
    def __init__(self, ratings_path: Optional[str] = None) -> None:
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
        # Tasks that remove rooms after a period of inactivity
        self.cleanup_tasks: Dict[str, Optional[asyncio.Task]] = {}
        # Elo-style ratings for players by name
        self.ratings_path = (
            Path(ratings_path)
            if ratings_path is not None
            else Path(__file__).with_name("ratings.json")
        )
        self.ratings: Dict[str, int] = self._load_ratings()
        # Track which seats are occupied by bots. Values are bot names.
        self.bots: Dict[str, Dict[str, Optional[str]]] = {}
        self._counter = 1

    def create_game(self) -> str:
        """Create a new empty game and return its id."""
        game_id = str(self._counter)
        self._counter += 1
        self.active[game_id] = {"black": None, "white": None}
        self.games[game_id] = Game()
        self.names[game_id] = {"black": "", "white": ""}
        self.bots[game_id] = {"black": None, "white": None}
        self.release_tasks[game_id] = {"black": None, "white": None}
        self.watchers[game_id] = set()
        self.room_names[game_id] = f"Game {game_id}"
        self._schedule_room_cleanup(game_id)
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
            self.bots[game_id] = {"black": None, "white": None}
            self.release_tasks[game_id] = {"black": None, "white": None}
            self.watchers[game_id] = set()
            self.room_names.setdefault(game_id, f"Game {game_id}")
        players = self.active[game_id]
        names = self.names[game_id]

        color: Optional[str] = None
        if (
            name
            and names.get("black") == name
            and players["black"] is None
            and self.bots.get(game_id, {}).get("black") is None
        ):
            color = "black"
        elif (
            name
            and names.get("white") == name
            and players["white"] is None
            and self.bots.get(game_id, {}).get("white") is None
        ):
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
        self._schedule_room_cleanup(game_id)
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
                self._schedule_room_cleanup(game_id)

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
                        "ratings": self.get_game_ratings(game_id),
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

    # Rating utilities
    def _load_ratings(self) -> Dict[str, int]:
        try:
            with self.ratings_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: int(v) for k, v in data.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_ratings(self) -> None:
        try:
            with self.ratings_path.open("w", encoding="utf-8") as f:
                json.dump(self.ratings, f)
        except OSError:
            pass

    def get_rating(self, name: str) -> int:
        """Return the current rating for ``name`` defaulting to 1500."""
        return self.ratings.get(name, 1500)

    def get_game_ratings(self, game_id: str) -> Dict[str, int]:
        names = self.names.get(game_id, {})
        return {
            "black": self.get_rating(names.get("black", "")),
            "white": self.get_rating(names.get("white", "")),
        }

    def update_ratings(self, game_id: str) -> None:
        names = self.names.get(game_id)
        game = self.games.get(game_id)
        if not names or not game:
            return
        black_name = names.get("black")
        white_name = names.get("white")
        if not black_name or not white_name:
            return
        black_score, white_score = game.score()
        if black_score > white_score:
            result = 1
        elif white_score > black_score:
            result = -1
        else:
            result = 0
        rb = self.get_rating(black_name)
        rw = self.get_rating(white_name)
        expected_black = 1 / (1 + 10 ** ((rw - rb) / 400))
        expected_white = 1 - expected_black
        k = 32
        if result == 1:
            sb, sw = 1.0, 0.0
        elif result == -1:
            sb, sw = 0.0, 1.0
        else:
            sb = sw = 0.5
        self.ratings[black_name] = rb + round(k * (sb - expected_black))
        self.ratings[white_name] = rw + round(k * (sw - expected_white))
        self._save_ratings()

    def claim_seat(self, game_id: str, websocket: WebSocket, color: str, name: str) -> bool:
        """Attempt to assign ``websocket`` the requested seat."""
        players = self.active.get(game_id)
        names = self.names.get(game_id)
        if not players or not names:
            return False
        if (
            players[color] is None
            and self.bots.get(game_id, {}).get(color) is None
            and (names[color] in ("", name))
        ):
            players[color] = websocket
            names[color] = name
            self.watchers.get(game_id, set()).discard(websocket)
            # Cancel any pending release task
            task = self.release_tasks.get(game_id, {}).get(color)
            if task:
                task.cancel()
                self.release_tasks[game_id][color] = None
            self._schedule_room_cleanup(game_id)
            return True
        return False

    def add_bot(self, game_id: str, color: str, bot_name: str) -> bool:
        """Seat ``bot_name`` in the given ``color`` if the seat is empty."""
        players = self.active.get(game_id)
        names = self.names.get(game_id)
        bots = self.bots.get(game_id)
        if not players or not names or not bots or bot_name not in BOTS:
            return False
        if players[color] is None and bots[color] is None:
            names[color] = bot_name
            bots[color] = bot_name
            self._schedule_room_cleanup(game_id)
            return True
        return False

    async def bot_move(self, game_id: str) -> None:
        """Have any seated bots play their moves until it's a human turn."""
        game = self.games.get(game_id)
        if not game:
            return
        bots = self.bots.get(game_id, {})
        while True:
            current = game.current_player
            if current == 0:
                break
            color = "black" if current == 1 else "white"
            bot_name = bots.get(color)
            if bot_name is None:
                break
            strategy = BOTS.get(bot_name)
            move = strategy(game, current) if strategy else None
            if move:
                x, y = move
                game.make_move(x, y, current)
            else:
                # No valid moves: pass
                game.current_player = -current
                if not game.valid_moves(game.current_player):
                    game.current_player = 0
            if game.current_player == 0:
                self.update_ratings(game_id)
            await self.broadcast(
                game_id,
                {
                    "type": "update",
                    "board": game.board,
                    "last": game.last_move,
                    "current": game.current_player,
                    "players": self.names[game_id],
                    "ratings": self.get_game_ratings(game_id),
                },
            )

    def restart_game(self, game_id: str) -> bool:
        """Reset the board for ``game_id`` while retaining players.

        Returns ``True`` if the game existed and was reset.
        """
        if game_id not in self.games:
            return False
        self.games[game_id] = Game()
        return True

    def _remove_room(self, game_id: str) -> None:
        """Remove all traces of a room."""
        for task in self.release_tasks.get(game_id, {}).values():
            if task:
                task.cancel()
        self.release_tasks.pop(game_id, None)
        self.watchers.pop(game_id, None)
        self.active.pop(game_id, None)
        self.games.pop(game_id, None)
        self.names.pop(game_id, None)
        self.bots.pop(game_id, None)
        self.room_names.pop(game_id, None)

    def _schedule_room_cleanup(self, game_id: str) -> None:
        """Schedule removal of a room based on player occupancy."""
        players = self.active.get(game_id)
        bots = self.bots.get(game_id, {})
        if players is None:
            return
        existing = self.cleanup_tasks.get(game_id)
        if existing:
            existing.cancel()

        def seat_empty(color: str) -> bool:
            return players[color] is None and bots.get(color) is None

        if seat_empty("black") and seat_empty("white"):
            delay = 5 * 60
        elif seat_empty("black") or seat_empty("white"):
            delay = 30 * 60
        else:
            self.cleanup_tasks[game_id] = None
            return
        self.cleanup_tasks[game_id] = asyncio.create_task(
            self._remove_after_delay(game_id, delay)
        )

    async def _remove_after_delay(self, game_id: str, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            players = self.active.get(game_id)
            bots = self.bots.get(game_id, {})
            if not players:
                return
            if (
                (players["black"] is None and bots.get("black") is None)
                or (players["white"] is None and bots.get("white") is None)
            ):
                # Remove whether missing one or all players
                self._remove_room(game_id)
        finally:
            self.cleanup_tasks.pop(game_id, None)


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
                "last": game.last_move,
                "color": color,
                "current": game.current_player,
                "players": manager.names[game_id],
                "ratings": manager.get_game_ratings(game_id),
                "bots": list(BOTS.keys()),
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
                    if game.current_player == 0:
                        manager.update_ratings(game_id)
                    await manager.broadcast(
                        game_id,
                        {
                            "type": "update",
                            "board": game.board,
                            "last": game.last_move,
                            "current": game.current_player,
                            "players": manager.names[game_id],
                            "ratings": manager.get_game_ratings(game_id),
                        },
                    )
                    await manager.bot_move(game_id)
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
                            "ratings": manager.get_game_ratings(game_id),
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
                            "ratings": manager.get_game_ratings(game_id),
                        },
                    )
                    await manager.bot_move(game_id)
                else:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Seat taken"}))
            elif action == "bot":
                requested = msg.get("color")
                bot_name = msg.get("bot", "")
                if (
                    color
                    and requested in ("black", "white")
                    and requested != color
                    and manager.add_bot(game_id, requested, bot_name)
                ):
                    await manager.broadcast(
                        game_id,
                        {
                            "type": "players",
                            "players": manager.names[game_id],
                            "current": game.current_player,
                            "ratings": manager.get_game_ratings(game_id),
                        },
                    )
                    await manager.bot_move(game_id)
                else:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Seat taken"}))
            elif action == "chat":
                # Broadcast chat messages to all players and spectators
                text = msg.get("message", "")
                sender = msg.get("name", "")
                if text:
                    await manager.broadcast(
                        game_id,
                        {"type": "chat", "name": sender, "message": text},
                    )
            elif action == "restart":
                if color and game.current_player == 0:
                    manager.restart_game(game_id)
                    game = manager.games[game_id]
                    await manager.broadcast(
                        game_id,
                        {
                            "type": "update",
                            "board": game.board,
                            "last": game.last_move,
                            "current": game.current_player,
                            "players": manager.names[game_id],
                            "ratings": manager.get_game_ratings(game_id),
                        },
                    )
                    await manager.bot_move(game_id)
                else:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "Cannot restart"})
                    )
    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

