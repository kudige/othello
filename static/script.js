let socket;
let playerColor = null;
let playerName = localStorage.getItem('playerName');
// Track the latest board state and whose turn it is so we can re-render
// the board if the user takes a seat after initially joining as a
// spectator. Without storing this information, the board would still be
// rendered for a spectator and the newly seated player would be unable to
// make a move until a full page refresh.
let currentBoard = null;
let currentTurn = 0;
let currentPlayers = null;
let currentRatings = null;
let currentSpectators = [];
const gameId = window.location.pathname.split('/').pop();
let availableBots = [];
// Track the last move sent by the server so we can highlight it.
let lastMove = null;

function connect() {
    if (!gameId) {
        return;
    }
    if (!playerName) {
        playerName = prompt('Enter your name');
        if (playerName) {
            localStorage.setItem('playerName', playerName);
        }
    }
    const nameParam = playerName ? `?name=${encodeURIComponent(playerName)}` : '';
    const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + `/ws/${gameId}${nameParam}`;
    socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'init') {
            playerColor = msg.color;
            currentBoard = msg.board;
            currentTurn = msg.current;
            currentPlayers = msg.players;
            currentRatings = msg.ratings;
            currentSpectators = msg.spectators || [];
            lastMove = msg.last;
            availableBots = msg.bots || [];
            renderBoard(currentBoard, currentTurn, lastMove);
            renderPlayers(currentPlayers, currentSpectators, currentTurn);
            if (playerName) {
                socket.send(JSON.stringify({action: 'name', name: playerName}));
            }
        } else if (msg.type === 'update') {
            currentBoard = msg.board;
            currentTurn = msg.current;
            currentPlayers = msg.players;
            currentRatings = msg.ratings;
            currentSpectators = msg.spectators || [];
            lastMove = msg.last;
            renderBoard(currentBoard, currentTurn, lastMove);
            renderPlayers(currentPlayers, currentSpectators, currentTurn);
        } else if (msg.type === 'players') {
            currentPlayers = msg.players;
            currentTurn = msg.current;
            currentRatings = msg.ratings;
            currentSpectators = msg.spectators || [];
            renderPlayers(currentPlayers, currentSpectators, currentTurn);
        } else if (msg.type === 'chat') {
            appendChat(msg.name, msg.message);
        } else if (msg.type === 'seat') {
            playerColor = msg.color;
            if (playerName) {
                socket.send(JSON.stringify({action: 'name', name: playerName}));
            }
            // Re-render the board and player list so the newly seated player
            // can immediately interact with the game without refreshing.
            if (currentBoard) {
                renderBoard(currentBoard, currentTurn, lastMove);
            }
            if (currentPlayers) {
                renderPlayers(currentPlayers, currentSpectators, currentTurn);
            }
        } else if (msg.type === 'error') {
            alert(msg.message);
        }
    };
}

function renderBoard(board, current, last) {
    const boardDiv = document.getElementById('board');
    boardDiv.innerHTML = '';
    const turnColor = current === 1 ? 'black' : current === -1 ? 'white' : null;
    const valid = new Set();
    if (turnColor) {
        validMoves(board, current).forEach(([vx, vy]) => valid.add(`${vx},${vy}`));
    }
    let blackCount = 0;
    let whiteCount = 0;
    board.forEach((row, x) => {
        row.forEach((cell, y) => {
            const cellDiv = document.createElement('div');
            cellDiv.className = 'cell';
            const key = `${x},${y}`;
            if (
                cell === 0 &&
                playerColor === turnColor &&
                valid.has(key)
            ) {
                cellDiv.classList.add('valid');
                cellDiv.onclick = () => sendMove(x, y);
            }
            if (cell !== 0) {
                const disc = document.createElement('div');
                disc.className = 'disc ' + (cell === 1 ? 'black' : 'white');
                if (last && last[0] === x && last[1] === y) {
                    disc.classList.add('last');
                }
                cellDiv.appendChild(disc);
                if (cell === 1) {
                    blackCount++;
                } else if (cell === -1) {
                    whiteCount++;
                }
            }
            boardDiv.appendChild(cellDiv);
        });
    });
    document.getElementById('black-count').textContent = blackCount;
    document.getElementById('white-count').textContent = whiteCount;
    const messageDiv = document.getElementById('message');
    if (current === 0) {
        let msg;
        if (blackCount > whiteCount) {
            msg = 'Game over! Black wins.';
        } else if (whiteCount > blackCount) {
            msg = 'Game over! White wins.';
        } else {
            msg = "Game over! It's a draw.";
        }
        messageDiv.textContent = msg + ' ';
        if (playerColor) {
            const btn = document.createElement('button');
            btn.textContent = 'Restart';
            btn.onclick = sendRestart;
            messageDiv.appendChild(btn);
        }
    } else {
        messageDiv.textContent = '';
    }
}

function renderPlayers(players, spectators, current) {
    const blackPlayer = document.getElementById('black-player');
    const whitePlayer = document.getElementById('white-player');
    const blackName = document.getElementById('black-name');
    const whiteName = document.getElementById('white-name');

    // Helper to render a seat
    function renderSeat(color, el, name) {
        el.innerHTML = '';
        if (name) {
            el.textContent = name;
            if (playerColor === color) {
                el.textContent += ' (You)';
            }
        } else if (!playerColor) {
            const btn = document.createElement('button');
            btn.textContent = 'Sit';
            btn.onclick = () => {
                socket.send(JSON.stringify({action: 'sit', color: color, name: playerName}));
            };
            el.appendChild(btn);
        } else if (playerColor !== color) {
            if (availableBots.length > 0) {
                const btn = document.createElement('button');
                btn.textContent = 'Invite Bot';
                btn.onclick = () => {
                    openBotPopup(color);
                };
                el.appendChild(btn);
            }
        } else {
            el.textContent = 'Waiting...';
        }
    }

    renderSeat('black', blackName, players.black);
    renderSeat('white', whiteName, players.white);

    blackPlayer.classList.toggle('you', playerColor === 'black');
    whitePlayer.classList.toggle('you', playerColor === 'white');

    const list = document.getElementById('player-names');
    if (list) {
        list.innerHTML = '';
        const entries = [];
        if (players.black) entries.push({label: 'Black', name: players.black});
        if (players.white) entries.push({label: 'White', name: players.white});
        spectators.forEach((n) => {
            if (n) entries.push({label: 'Spectator', name: n});
        });
        entries.forEach((e) => {
            const li = document.createElement('li');
            li.textContent = e.label ? `${e.label}: ${e.name}` : e.name;
            if (e.name === playerName) {
                li.textContent += ' (You)';
            }
            list.appendChild(li);
        });
    }
}

function openBotPopup(color) {
    const existing = document.getElementById('bot-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'bot-overlay';
    overlay.className = 'overlay';

    const popup = document.createElement('div');
    popup.className = 'popup';

    const title = document.createElement('h2');
    title.textContent = 'Select a Bot';
    popup.appendChild(title);

    availableBots.forEach((b) => {
        const opt = document.createElement('div');
        opt.className = 'bot-option';
        opt.textContent = b;
        opt.onclick = () => {
            socket.send(JSON.stringify({action: 'bot', color: color, bot: b}));
            overlay.remove();
        };
        popup.appendChild(opt);
    });

    overlay.onclick = (e) => {
        if (e.target === overlay) {
            overlay.remove();
        }
    };

    overlay.appendChild(popup);
    document.body.appendChild(overlay);
}

function validMoves(board, player) {
    const moves = [];
    for (let x = 0; x < board.length; x++) {
        for (let y = 0; y < board[x].length; y++) {
            if (board[x][y] === 0 && captures(board, x, y, player).length > 0) {
                moves.push([x, y]);
            }
        }
    }
    return moves;
}

function captures(board, x, y, player) {
    const opponent = -player;
    const captured = [];
    const dirs = [
        [-1, -1], [0, -1], [1, -1],
        [-1, 0],           [1, 0],
        [-1, 1],  [0, 1],  [1, 1]
    ];
    for (const [dx, dy] of dirs) {
        let nx = x + dx;
        let ny = y + dy;
        const temp = [];
        while (nx >= 0 && nx < 8 && ny >= 0 && ny < 8 && board[nx][ny] === opponent) {
            temp.push([nx, ny]);
            nx += dx;
            ny += dy;
        }
        if (nx >= 0 && nx < 8 && ny >= 0 && ny < 8 && board[nx][ny] === player && temp.length > 0) {
            captured.push(...temp);
        }
    }
    return captured;
}

function sendMove(x, y) {
    if (socket && playerColor) {
        socket.send(JSON.stringify({action: 'move', x: x, y: y, color: playerColor}));
    }
}

function sendRestart() {
    if (socket && playerColor) {
        socket.send(JSON.stringify({action: 'restart'}));
    }
}

function appendChat(name, message) {
    const log = document.getElementById('chat-log');
    const entry = document.createElement('div');
    entry.textContent = (name ? name : 'Anon') + ': ' + message;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function sendChat(e) {
    e.preventDefault();
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (text && socket) {
        socket.send(JSON.stringify({action: 'chat', name: playerName, message: text}));
        input.value = '';
    }
}
function init() {
    connect();
    const form = document.getElementById('chat-form');
    if (form) {
        form.addEventListener('submit', sendChat);
    }
}

window.onload = init;
