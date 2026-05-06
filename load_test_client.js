const { Room } = require('livekit-client');

async function connect() {
  const room = new Room();
  const serverUrl = process.env.LIVEKIT_URL;
  const token = process.env.TOKEN;

  console.log("Connecting to LiveKit...");
  await room.connect(serverUrl, token);
  console.log("Connected!");
  await new Promise(() => {});
}

connect().catch(console.error);
