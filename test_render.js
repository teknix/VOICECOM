const fs = require('fs');
const content = fs.readFileSync('app/templates/voice.html', 'utf8');
const lines = content.split('\n');
let found = false;
for (let i = 0; i < lines.length; i++) {
  if (lines[i].includes('function renderFloor')) {
    console.log(lines.slice(i, i+50).join('\n'));
    found = true;
    break;
  }
}
