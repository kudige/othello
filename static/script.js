let socket;
let playerColor = null;

function connect() {
    const gameId = prompt("Enter game ID");
    const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + `/ws/${gameId}`;
    socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'init') {
            playerColor = msg.color;
            renderBoard(msg.board);
        } else if (msg.type === 'update') {
            renderBoard(msg.board);
        } else if (msg.type === 'error') {
            alert(msg.message);
        }
    };
}

function renderBoard(board) {
    const boardDiv = document.getElementById('board');
    boardDiv.innerHTML = '';
    board.forEach((col, x) => {
        col.forEach((cell, y) => {
            const cellDiv = document.createElement('div');
            cellDiv.className = 'cell';
            cellDiv.dataset.x = x;
            cellDiv.dataset.y = y;
            cellDiv.onclick = () => sendMove(x, y);
            if (cell !== 0) {
                const disc = document.createElement('div');
                disc.className = 'disc ' + (cell === 1 ? 'black' : 'white');
                cellDiv.appendChild(disc);
            }
            boardDiv.appendChild(cellDiv);
        });
    });
}

function sendMove(x, y) {
    if (socket && playerColor) {
        socket.send(JSON.stringify({action: 'move', x: x, y: y, color: playerColor}));
    }
}

window.onload = connect;
