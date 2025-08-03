let socket;
let playerColor = null;
let playerName = null;

function connect() {
    const gameId = prompt("Enter game ID");
    playerName = prompt("Enter your name");
    const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + `/ws/${gameId}`;
    socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'init') {
            playerColor = msg.color;
            renderBoard(msg.board, msg.current);
            renderPlayers(msg.players, msg.current);
            if (playerName) {
                socket.send(JSON.stringify({action: 'name', name: playerName}));
            }
        } else if (msg.type === 'update') {
            renderBoard(msg.board, msg.current);
            renderPlayers(msg.players, msg.current);
        } else if (msg.type === 'players') {
            renderPlayers(msg.players, msg.current);
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
            }
            boardDiv.appendChild(cellDiv);
        });
    });
}

function renderPlayers(players, current) {
    document.getElementById('black-name').textContent = players.black || 'Waiting...';
    document.getElementById('white-name').textContent = players.white || 'Waiting...';
    document.getElementById('black-player').classList.toggle('active', current === 1);
    document.getElementById('white-player').classList.toggle('active', current === -1);
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
