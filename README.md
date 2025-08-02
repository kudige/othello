# othello

Multiplayer browser-based Othello game with a Python backend and WebSocket communication.

## Setup

```bash
pip install -r requirements.txt
```

## Running the server

```bash
uvicorn backend.server:app --reload
```

Open the browser at `http://localhost:8000` and enter the same game ID in two different windows to play against another player.
