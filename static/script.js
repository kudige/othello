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
const gameId = window.location.pathname.split('/').pop();

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
            renderBoard(currentBoard, currentTurn);
            renderPlayers(currentPlayers, currentTurn);
            if (playerName && playerColor) {
                socket.send(JSON.stringify({action: 'name', name: playerName}));
            }
        } else if (msg.type === 'update') {
            currentBoard = msg.board;
            currentTurn = msg.current;
            currentPlayers = msg.players;
            renderBoard(currentBoard, currentTurn);
            renderPlayers(currentPlayers, currentTurn);
        } else if (msg.type === 'players') {
            currentPlayers = msg.players;
            currentTurn = msg.current;
            renderPlayers(currentPlayers, currentTurn);
        } else if (msg.type === 'seat') {
            playerColor = msg.color;
            if (playerName) {
                socket.send(JSON.stringify({action: 'name', name: playerName}));
            }
            // Re-render the board and player list so the newly seated player
            // can immediately interact with the game without refreshing.
            if (currentBoard) {
                renderBoard(currentBoard, currentTurn);
            }
            if (currentPlayers) {
                renderPlayers(currentPlayers, currentTurn);
            }
        } else if (msg.type === 'error') {
            alert(msg.message);
        }
    };
}

function renderBoard(board, current) {
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
        if (blackCount > whiteCount) {
            messageDiv.textContent = 'Game over! Black wins.';
        } else if (whiteCount > blackCount) {
            messageDiv.textContent = 'Game over! White wins.';
        } else {
            messageDiv.textContent = "Game over! It's a draw.";
        }
    } else {
        messageDiv.textContent = '';
    }
}

function renderPlayers(players, current) {
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
        } else {
            el.textContent = 'Waiting...';
        }
    }

    renderSeat('black', blackName, players.black);
    renderSeat('white', whiteName, players.white);

    blackPlayer.classList.toggle('active', current === 1);
    whitePlayer.classList.toggle('active', current === -1);

    blackPlayer.classList.toggle('you', playerColor === 'black');
    whitePlayer.classList.toggle('you', playerColor === 'white');
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

window.onload = connect;
