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
        const li = document.createElement('li');
        const black = room.players.black || '---';
        const white = room.players.white || '---';
        li.textContent = `${room.name} (Black: ${black}, White: ${white})`;
        li.onclick = () => {
            window.location.href = `/game/${room.id}`;
        };
        list.appendChild(li);
    });
}

setInterval(fetchRooms, 2000);
fetchRooms();

document.getElementById('create-room').onclick = async () => {
    const res = await fetch('/create', {method: 'POST'});
    const data = await res.json();
    window.location.href = `/game/${data.id}`;
};
