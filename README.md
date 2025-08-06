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

## Static assets

Static files are served with a version query string (e.g. `/static/script.js?3`).
The number is automatically derived from the Git revision history for that file
so it changes whenever the asset is updated. This ensures browsers always fetch
the latest copy without relying on manual cache busting. When adding or
modifying files in the `static/` directory, simply commit them and the server
will append the appropriate tag.
