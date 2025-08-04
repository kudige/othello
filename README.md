# othello

Multiplayer browser-based Othello game with a Python backend and WebSocket communication.

**Note:** In this version of the game, the white player moves first.

## Setup

```bash
pip install -r requirements.txt
```

## Running the server

```bash
uvicorn backend.server:app --host 0.0.0.0 --reload
```

Open the browser at `http://localhost:8000` and enter the same game ID in two different windows to play against another player.
