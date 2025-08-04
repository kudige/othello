let playerName = localStorage.getItem('playerName');
if (!playerName) {
    playerName = prompt('Enter your name');
    if (playerName) {
        localStorage.setItem('playerName', playerName);
    }
}
if (playerName) {
    document.getElementById('welcome').textContent = `Welcome, ${playerName}`;
}

async function fetchRooms() {
    const res = await fetch('/rooms');
    const data = await res.json();
    const list = document.getElementById('rooms');
    list.innerHTML = '';
    data.rooms.forEach(room => {
        const div = document.createElement('div');
        div.className = 'room';
        const players = [];
        if (room.players.white) players.push(room.players.white);
        if (room.players.black) players.push(room.players.black);
        const names = players.length ? players.join(', ') : '---';
        div.textContent = `${room.name} (${names})`;
        div.onclick = () => {
            window.location.href = `/game/${room.id}`;
        };
        list.appendChild(div);
    });
}

setInterval(fetchRooms, 2000);
fetchRooms();

document.getElementById('create-room').onclick = async () => {
    const res = await fetch('/create', {method: 'POST'});
    const room = await res.json();
    window.location.href = `/game/${room.id}`;
};
