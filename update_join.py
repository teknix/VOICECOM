import re

with open('app/templates/voice.html', 'r') as f:
    content = f.read()

new_content = content.replace(
    'async function joinRoom(roomId, displayName, mode) {',
    'async function joinRoom(roomId, displayName, mode) { console.log("joinRoom called for", roomId);'
)

with open('app/templates/voice.html', 'w') as f:
    f.write(new_content)
