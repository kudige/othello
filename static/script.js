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
const gameId = window.location.pathname.split('/').pop();
let availableBots = [];
// Track the last move sent by the server so we can highlight it.
let lastMove = null;
// History of board states for replay and saving.
let moveHistory = [];
let replayTimer = null;
let replayIdx = 0;
let replayPaused = false;
let isReplaying = false;

function cloneBoard(board) {
    return board.map(row => row.slice());
}

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
            lastMove = msg.last;
            availableBots = msg.bots || [];
            moveHistory = [{board: cloneBoard(msg.board), current: msg.current, last: msg.last}];
            renderBoard(currentBoard, currentTurn, lastMove);
            renderPlayers(currentPlayers, currentTurn);
            if (playerName && playerColor) {
                socket.send(JSON.stringify({action: 'name', name: playerName}));
            }
        } else if (msg.type === 'update') {
            currentBoard = msg.board;
            currentTurn = msg.current;
            currentPlayers = msg.players;
            currentRatings = msg.ratings;
            lastMove = msg.last;
            moveHistory.push({board: cloneBoard(msg.board), current: msg.current, last: msg.last});
            renderBoard(currentBoard, currentTurn, lastMove);
            renderPlayers(currentPlayers, currentTurn);
        } else if (msg.type === 'players') {
            currentPlayers = msg.players;
            currentTurn = msg.current;
            currentRatings = msg.ratings;
            renderPlayers(currentPlayers, currentTurn);
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
                renderPlayers(currentPlayers, currentTurn);
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
                valid.has(key) &&
                !isReplaying
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
        const replayBtn = document.createElement('button');
        replayBtn.textContent = 'Replay';
        replayBtn.onclick = startReplay;
        messageDiv.appendChild(replayBtn);
        messageDiv.appendChild(document.createTextNode(' '));
        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save Game';
        saveBtn.onclick = saveGame;
        messageDiv.appendChild(saveBtn);
        if (playerColor) {
            messageDiv.appendChild(document.createTextNode(' '));
            const btn = document.createElement('button');
            btn.textContent = 'Restart';
            btn.onclick = sendRestart;
            messageDiv.appendChild(btn);
            messageDiv.appendChild(document.createTextNode(' '));
            const standBtn = document.createElement('button');
            standBtn.textContent = 'Stand Up';
            standBtn.onclick = sendStand;
            messageDiv.appendChild(standBtn);
        }
    } else {
        messageDiv.textContent = '';
    }
}

function renderPlayers(players, current) {
    const blackName = document.getElementById('black-name');
    const whiteName = document.getElementById('white-name');
    const blackScore = document.getElementById('black-score');
    const whiteScore = document.getElementById('white-score');

    // Helper to render a seat
    function renderSeat(color, nameEl, scoreEl, name) {
        nameEl.innerHTML = '';
        scoreEl.textContent = '';
        if (name) {
            let display = name;
            if (playerColor === color) {
                display += ' (you)';
            }
            const rating = currentRatings && currentRatings[color];
            if (rating) {
                scoreEl.textContent = `(${rating})`;
            }
            nameEl.textContent = display;
        } else if (!playerColor) {
            const btn = document.createElement('button');
            btn.textContent = 'Sit';
            btn.onclick = () => {
                socket.send(JSON.stringify({action: 'sit', color: color, name: playerName}));
            };
            nameEl.appendChild(btn);
        } else if (playerColor !== color) {
            if (availableBots.length > 0) {
                const btn = document.createElement('button');
                btn.textContent = 'Invite Bot';
                btn.onclick = () => {
                    openBotPopup(color);
                };
                nameEl.appendChild(btn);
            }
        } else {
            nameEl.textContent = 'Waiting...';
        }
    }

    renderSeat('white', whiteName, whiteScore, players.white);
    renderSeat('black', blackName, blackScore, players.black);
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
        moveHistory = [];
        socket.send(JSON.stringify({action: 'restart'}));
    }
}

function sendStand() {
    if (socket && playerColor) {
        socket.send(JSON.stringify({action: 'stand'}));
    }
}

function startReplay() {
    if (replayTimer) {
        clearInterval(replayTimer);
    }
    if (moveHistory.length === 0) {
        return;
    }
    isReplaying = true;
    replayIdx = 0;
    replayPaused = false;
    const boardDiv = document.getElementById('board');
    boardDiv.onclick = toggleReplay;
    advanceReplay();
    replayTimer = setInterval(advanceReplay, 1000);
}

function advanceReplay() {
    if (replayPaused) {
        updateReplayMessage();
        return;
    }
    replayIdx++;
    if (replayIdx >= moveHistory.length) {
        clearInterval(replayTimer);
        replayTimer = null;
        isReplaying = false;
        const boardDiv = document.getElementById('board');
        boardDiv.onclick = null;
        const last = moveHistory[moveHistory.length - 1];
        renderBoard(last.board, last.current, last.last);
        return;
    }
    const snap = moveHistory[replayIdx];
    renderBoard(snap.board, snap.current, snap.last);
    updateReplayMessage();
}

function toggleReplay() {
    replayPaused = !replayPaused;
    updateReplayMessage();
}

function stepReplay(delta) {
    replayIdx = Math.max(0, Math.min(replayIdx + delta, moveHistory.length - 1));
    const snap = moveHistory[replayIdx];
    renderBoard(snap.board, snap.current, snap.last);
    updateReplayMessage();
}

function updateReplayMessage() {
    const messageDiv = document.getElementById('message');
    const total = Math.max(moveHistory.length - 1, 0);
    const move = Math.min(replayIdx, total);
    let text = `Replaying: move ${move}/${total}`;
    if (replayPaused) {
        text += ' (paused)';
    }
    messageDiv.textContent = text;
    if (replayPaused) {
        const backBtn = document.createElement('button');
        backBtn.textContent = '<';
        backBtn.onclick = () => stepReplay(-1);
        messageDiv.appendChild(document.createTextNode(' '));
        messageDiv.appendChild(backBtn);
        const fwdBtn = document.createElement('button');
        fwdBtn.textContent = '>';
        fwdBtn.onclick = () => stepReplay(1);
        messageDiv.appendChild(document.createTextNode(' '));
        messageDiv.appendChild(fwdBtn);
    }
}

function saveGame() {
    if (moveHistory.length === 0) {
        return;
    }
    const data = JSON.stringify({history: moveHistory});
    const blob = new Blob([data], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `othello_${gameId}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function handleLoadFile(ev) {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            if (Array.isArray(data.history) && data.history.length > 0) {
                moveHistory = data.history.slice(0, -1);
                const last = data.history[data.history.length - 1];
                if (socket) {
                    socket.send(JSON.stringify({action: 'load', data: last}));
                }
            }
        } catch (err) {
            alert('Invalid file');
        }
    };
    reader.readAsText(file);
    ev.target.value = '';
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
    const loadBtn = document.getElementById('load-game');
    const loadInput = document.getElementById('load-file');
    if (loadBtn && loadInput) {
        loadBtn.onclick = () => loadInput.click();
        loadInput.addEventListener('change', handleLoadFile);
    }
}

window.onload = init;
