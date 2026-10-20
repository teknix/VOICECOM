// Phone lab: join a test room, toggle keep-alive tricks, and log everything the
// browser does while the app is in the background or the screen is off.
// The log lives in localStorage so it survives the page being frozen or reloaded,
// and can be saved to the server (/teknix/log) to read back after a test.
(() => {
  const $ = (id) => document.getElementById(id);
  const LK = window.LivekitClient;
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode: keep going */ } },
  };

  // ── Run + log ──────────────────────────────────────────
  let run = store.get("lab.run", null) || newRunId();
  let events = store.get("lab.events." + run, []);
  store.set("lab.run", run);

  function newRunId() {
    const d = new Date();
    return d.toISOString().slice(0, 19).replace(/[-:T]/g, "") + "-" + Math.random().toString(36).slice(2, 6);
  }
  function stamp() {
    const d = new Date();
    return d.toLocaleTimeString([], { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
  }
  let saveTimer = null;
  function log(msg) {
    const line = `${stamp()}  ${msg}`;
    events.push(line);
    if (events.length > 5000) events = events.slice(-5000);
    const box = $("log");
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    box.append(line + "\n");
    if (atBottom) box.scrollTop = box.scrollHeight;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => store.set("lab.events." + run, events), 300);
  }
  function renderLog() {
    $("log").textContent = events.length ? events.join("\n") + "\n" : "";
    $("log").scrollTop = $("log").scrollHeight;
  }

  // ── Settings ───────────────────────────────────────────
  const OPTS = ["wakelock", "video", "media", "autopip", "callvideo"];
  const settings = store.get("lab.settings", {});
  function settingsNow() {
    const s = {};
    for (const o of OPTS) s[o] = $("opt-" + o).checked;
    return s;
  }
  function describeSettings() {
    const s = settingsNow();
    return OPTS.map((o) => `${o}=${s[o] ? "on" : "off"}`).join(" ");
  }

  // ── Room ───────────────────────────────────────────────
  let room = null, micOn = true, tone = null;
  const audioEls = new Map();          // track sid -> <audio>
  const audioTracks = new Map();       // track sid -> remote MediaStreamTrack (for the call video)

  function setStatus(text, cls) {
    const el = $("status");
    el.textContent = text;
    el.className = cls || "";
  }

  function people() {
    const ul = $("people");
    ul.textContent = "";
    if (!room) { ul.innerHTML = '<li class="muted">nobody yet</li>'; return; }
    const all = [room.localParticipant, ...room.remoteParticipants.values()];
    for (const p of all) {
      const li = document.createElement("li");
      li.textContent = (p.name || p.identity) + (p === room.localParticipant ? " (this device)" : "");
      ul.append(li);
    }
  }

  async function join() {
    const device = $("device").value.trim() || "device";
    store.set("lab.device", device);
    $("join").disabled = true;
    setStatus("connecting…");
    try {
      const res = await fetch("/teknix/token", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ device }),
      });
      if (!res.ok) throw new Error("token request failed (" + res.status + ")");
      const { token, identity } = await res.json();
      room = new LK.Room({ adaptiveStream: false, dynacast: false });
      wireRoom(room);
      await room.connect(LIVEKIT_WS_URL, token);
      log(`joined as ${identity} — ${describeSettings()}`);
      log(`browser: ${navigator.userAgent}`);
      await room.startAudio().catch(() => {});
      await room.localParticipant.setMicrophoneEnabled(true);
      micOn = true;
      $("leave").disabled = false;
      $("mic").disabled = false;
      $("tone").disabled = false;
      $("pip").disabled = false;
      $("fullscreen").disabled = false;
      setStatus("connected", "ok");
      people();
      applyAll();
    } catch (err) {
      log("join failed: " + err.message);
      setStatus("couldn't connect: " + err.message, "bad");
      $("join").disabled = false;
      room = null;
    }
  }

  async function leave(why) {
    if (!room) return;
    log("leaving" + (why ? ` (${why})` : ""));
    stopTone();
    await room.disconnect();
  }

  function wireRoom(r) {
    const E = LK.RoomEvent;
    r.on(E.ConnectionStateChanged, (s) => log(`connection: ${s}`));
    r.on(E.Reconnecting, () => { log("RECONNECTING"); setStatus("reconnecting…", "bad"); });
    r.on(E.Reconnected, () => { log("reconnected"); setStatus("connected", "ok"); });
    r.on(E.Disconnected, (reason) => {
      log(`DISCONNECTED (reason ${reason})`);
      setStatus("not connected", "bad");
      for (const el of audioEls.values()) el.remove();
      audioEls.clear();
      room = null;
      $("join").disabled = false;
      audioTracks.clear();
      updateCallVideo(true);
      for (const id of ["leave", "mic", "tone", "pip", "fullscreen"]) $(id).disabled = true;
      people();
      releaseWakeLock();
    });
    r.on(E.ParticipantConnected, (p) => { log(`${p.name || p.identity} joined`); people(); });
    r.on(E.ParticipantDisconnected, (p) => { log(`${p.name || p.identity} left`); people(); });
    r.on(E.TrackSubscribed, (track, pub, p) => {
      log(`receiving ${track.kind} "${pub.trackName || pub.source}" from ${p.name || p.identity}`);
      if (track.kind !== "audio") return;
      const el = track.attach();
      for (const ev of ["pause", "play", "stalled", "waiting", "suspend", "ended"]) {
        el.addEventListener(ev, () => log(`audio element ${ev} (${p.name || p.identity})`));
      }
      document.body.append(el);
      audioEls.set(track.sid, el);
      audioTracks.set(track.sid, track.mediaStreamTrack);
      updateCallVideo(true);
    });
    r.on(E.TrackUnsubscribed, (track, pub, p) => {
      log(`stopped receiving ${track.kind} from ${p.name || p.identity}`);
      const el = audioEls.get(track.sid);
      if (el) { el.remove(); audioEls.delete(track.sid); }
      audioTracks.delete(track.sid);
      updateCallVideo(true);
    });
    r.on(E.TrackMuted, (pub, p) => log(`${p.name || p.identity} ${pub.source} muted`));
    r.on(E.TrackUnmuted, (pub, p) => log(`${p.name || p.identity} ${pub.source} unmuted`));
    r.on(E.AudioPlaybackStatusChanged, () => log(`audio playback allowed: ${r.canPlaybackAudio}`));
    r.on(E.MediaDevicesError, (e) => log(`device error: ${e.message}`));
    r.on(E.LocalTrackPublished, (pub) => {
      const mst = pub.track && pub.track.mediaStreamTrack;
      if (!mst) return;
      const name = pub.trackName || pub.source;
      for (const ev of ["ended", "mute", "unmute"]) mst.addEventListener(ev, () => log(`my ${name} track: ${ev}`));
    });
  }

  async function toggleMic() {
    if (!room) return;
    micOn = !micOn;
    await room.localParticipant.setMicrophoneEnabled(micOn);
    $("mic").textContent = micOn ? "Mute my mic" : "Unmute my mic";
    log(micOn ? "mic on" : "mic muted");
    if ("mediaSession" in navigator && navigator.mediaSession.setMicrophoneActive) {
      try { navigator.mediaSession.setMicrophoneActive(micOn); } catch (e) { /* not supported */ }
    }
  }

  // ── Beep: 0.2 s of 660 Hz every second, from a looped buffer (no timers to throttle) ──
  async function startTone() {
    const ctx = new AudioContext();
    const sr = ctx.sampleRate, buf = ctx.createBuffer(1, sr, sr), ch = buf.getChannelData(0);
    for (let i = 0; i < sr * 0.2; i++) ch[i] = 0.4 * Math.sin(2 * Math.PI * 660 * i / sr);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const dest = ctx.createMediaStreamDestination();
    src.connect(dest);
    src.start();
    const track = new LK.LocalAudioTrack(dest.stream.getAudioTracks()[0], undefined, true);
    await room.localParticipant.publishTrack(track, { name: "beep" });
    ctx.addEventListener("statechange", () => log(`beep audio engine: ${ctx.state}`));
    tone = { ctx, src, track };
    $("tone").textContent = "Stop beep";
    log("beep started (this device)");
  }
  function stopTone() {
    if (!tone) return;
    try { room && room.localParticipant.unpublishTrack(tone.track); } catch (e) { /* already gone */ }
    tone.src.stop();
    tone.ctx.close();
    tone = null;
    $("tone").textContent = "Start beep (from this device)";
    log("beep stopped");
  }

  // ── Hearing check: log when each remote participant goes silent or comes back ──
  const heard = new Map();             // identity -> {sound: bool, since: ms}
  setInterval(() => {
    if (!room) return;
    const now = Date.now();
    for (const p of room.remoteParticipants.values()) {
      const sound = p.audioLevel > 0.005 || p.isSpeaking;
      const h = heard.get(p.identity);
      if (!h) { heard.set(p.identity, { sound, since: now }); continue; }
      if (sound !== h.sound) {
        const secs = ((now - h.since) / 1000).toFixed(1);
        log(sound ? `hearing ${p.name || p.identity} again (silent ${secs}s)` : `${p.name || p.identity} went silent (after ${secs}s of sound)`);
        heard.set(p.identity, { sound, since: now });
      }
    }
  }, 1000);

  // ── Timer heartbeat: shows when the browser froze this page ──
  let lastTick = Date.now();
  setInterval(() => {
    const now = Date.now(), gap = now - lastTick;
    if (gap > 2500) log(`page timers were paused for ${(gap / 1000).toFixed(1)}s`);
    lastTick = now;
  }, 1000);

  // ── Page lifecycle ─────────────────────────────────────
  document.addEventListener("visibilitychange", () => {
    log(`page ${document.visibilityState}`);
    if (document.visibilityState === "hidden") saveLog(true);
    else { if ($("opt-wakelock").checked) acquireWakeLock(); saveLog(false); }
  });
  window.addEventListener("pagehide", (e) => { log(`pagehide (persisted=${e.persisted})`); saveLog(true); });
  window.addEventListener("pageshow", (e) => log(`pageshow (persisted=${e.persisted})`));
  document.addEventListener("freeze", () => log("page frozen"));
  document.addEventListener("resume", () => log("page resumed"));
  window.addEventListener("focus", () => log("window focus"));
  window.addEventListener("blur", () => log("window blur"));
  window.addEventListener("online", () => log("network online"));
  window.addEventListener("offline", () => log("network OFFLINE"));

  // ── Wake Lock ──────────────────────────────────────────
  let wakeLock = null;
  async function acquireWakeLock() {
    if (!("wakeLock" in navigator)) { log("wake lock: not supported in this browser"); return; }
    if (wakeLock) return;
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      log("wake lock: on");
      wakeLock.addEventListener("release", () => { log("wake lock: released"); wakeLock = null; });
    } catch (err) { log("wake lock failed: " + err.message); }
  }
  function releaseWakeLock() { if (wakeLock) wakeLock.release(); }

  // ── Canvas: feeds the keep-awake video and the picture-in-picture window ──
  const canvas = $("pip-canvas"), g = canvas.getContext("2d");
  function drawCanvas() {
    g.fillStyle = "#111"; g.fillRect(0, 0, canvas.width, canvas.height);
    g.fillStyle = "#6c8cff"; g.font = "bold 22px system-ui"; g.fillText("VoiceCom lab", 14, 34);
    g.fillStyle = "#eee"; g.font = "16px system-ui";
    g.fillText(new Date().toLocaleTimeString([], { hour12: false }), 14, 60);
    let y = 90;
    if (room) {
      for (const p of room.remoteParticipants.values()) {
        const lvl = Math.min(1, p.audioLevel * 4);
        g.fillStyle = "#333"; g.fillRect(14, y - 12, 150, 12);
        g.fillStyle = "#4ade80"; g.fillRect(14, y - 12, 150 * lvl, 12);
        g.fillStyle = "#eee"; g.fillText((p.name || p.identity).slice(0, 22), 172, y);
        y += 24;
      }
      g.fillStyle = micOn ? "#4ade80" : "#f87171";
      g.fillText(micOn ? "mic on" : "mic muted", 14, canvas.height - 14);
    } else {
      g.fillText("not connected", 14, y);
    }
  }
  setInterval(drawCanvas, 250);
  drawCanvas();
  let canvasStream = null;
  function stream() { return canvasStream || (canvasStream = canvas.captureStream(4)); }

  // ── Keep-awake video ───────────────────────────────────
  async function applyVideo(on) {
    const v = $("keepawake");
    if (on) {
      v.srcObject = stream();
      try { await v.play(); log("keep-awake video: playing"); } catch (err) { log("keep-awake video failed: " + err.message); }
    } else if (v.srcObject) { v.pause(); v.srcObject = null; log("keep-awake video: off"); }
  }

  // ── Call video: the call's audio played by a <video> (canvas picture + every remote audio track) ──
  // Tests whether the browser keeps a playing video alive in the background where it
  // freezes an <audio>. While it's on, the <audio> elements are muted so nothing plays twice.
  const callVideo = $("callvideo");
  for (const ev of ["play", "pause", "stalled", "waiting", "suspend", "ended"]) {
    callVideo.addEventListener(ev, () => log(`call video ${ev}`));
  }
  callVideo.addEventListener("enterpictureinpicture", () => log("call video: picture-in-picture opened"));
  callVideo.addEventListener("leavepictureinpicture", () => log("call video: picture-in-picture closed"));
  async function updateCallVideo(quiet) {
    const on = $("opt-callvideo").checked && !!room;
    for (const el of audioEls.values()) el.muted = on;
    if (!on) {
      if (callVideo.srcObject) {
        callVideo.pause();
        callVideo.srcObject = null;
        if (!quiet) log("call video: off");
      }
      callVideo.hidden = true;
      return;
    }
    const tracks = [stream().getVideoTracks()[0], ...audioTracks.values()];
    callVideo.srcObject = new MediaStream(tracks);
    callVideo.muted = false;
    callVideo.hidden = false;
    try {
      await callVideo.play();
      log(`call video: playing (${audioTracks.size} call audio track${audioTracks.size === 1 ? "" : "s"})`);
    } catch (err) { log("call video failed: " + err.message); }
  }

  // ── Fullscreen the call video ──────────────────────────
  document.addEventListener("fullscreenchange", () => {
    const el = document.fullscreenElement;
    log(el ? `fullscreen: on (${el.id || el.tagName.toLowerCase()})` : "fullscreen: off");
  });
  document.addEventListener("fullscreenerror", () => log("fullscreen: refused by the browser"));
  async function goFullscreen() {
    if (!$("opt-callvideo").checked) {
      $("opt-callvideo").checked = true;
      settings.callvideo = true;
      store.set("lab.settings", settings);
      log("setting callvideo → on (for fullscreen)");
    }
    // No await before requestFullscreen: it must run inside the tap's user activation
    // (Firefox allows ~1 s). updateCallVideo sets srcObject synchronously before it awaits.
    const started = updateCallVideo(true);
    try {
      if (callVideo.requestFullscreen) await callVideo.requestFullscreen();
      else if (callVideo.webkitEnterFullscreen) callVideo.webkitEnterFullscreen();
      else log("fullscreen: not supported in this browser");
    } catch (err) { log("fullscreen failed: " + err.message); }
    await started;
  }

  // ── Picture-in-picture ─────────────────────────────────
  const pipVideo = $("pip-video");
  pipVideo.addEventListener("enterpictureinpicture", () => log("picture-in-picture: opened"));
  pipVideo.addEventListener("leavepictureinpicture", () => log("picture-in-picture: closed"));
  async function openPip() {
    if (!pipVideo.requestPictureInPicture) { log("picture-in-picture: not supported in this browser"); return; }
    try {
      pipVideo.srcObject = stream();
      await pipVideo.play();
      if (document.pictureInPictureElement === pipVideo) await document.exitPictureInPicture();
      else await pipVideo.requestPictureInPicture();
    } catch (err) { log("picture-in-picture failed: " + err.message); }
  }

  // ── Media Session ──────────────────────────────────────
  function setHandler(action, fn) {
    try { navigator.mediaSession.setActionHandler(action, fn); return true; } catch (e) { return false; }
  }
  function applyMedia(on) {
    if (!("mediaSession" in navigator)) { if (on) log("media session: not supported"); return; }
    if (on) {
      navigator.mediaSession.metadata = new MediaMetadata({ title: "VoiceCom lab call", artist: $("device").value || "this device", album: "VoiceCom" });
      navigator.mediaSession.playbackState = "playing";
      const got = [];
      if (setHandler("play", () => log("media key: play"))) got.push("play");
      if (setHandler("pause", () => log("media key: pause"))) got.push("pause");
      if (setHandler("hangup", () => { log("media key: hang up"); leave("hang up from controls"); })) got.push("hangup");
      if (setHandler("togglemicrophone", () => { log("media key: microphone"); toggleMic(); })) got.push("togglemicrophone");
      log(`media session: on (handlers: ${got.join(", ") || "none"})`);
    } else {
      for (const a of ["play", "pause", "hangup", "togglemicrophone"]) setHandler(a, null);
      navigator.mediaSession.metadata = null;
      navigator.mediaSession.playbackState = "none";
      log("media session: off");
    }
  }
  function applyAutoPip(on) {
    if (!("mediaSession" in navigator)) return;
    const ok = setHandler("enterpictureinpicture", on ? () => { log("auto picture-in-picture requested by browser"); openPip(); } : null);
    if (on) log(ok ? "auto picture-in-picture: armed" : "auto picture-in-picture: not supported in this browser");
  }

  function apply(o, on, quiet) {
    if (o === "wakelock") on ? acquireWakeLock() : releaseWakeLock();
    if (o === "video") applyVideo(on);
    if (o === "media") applyMedia(on);
    if (o === "autopip") applyAutoPip(on);
    if (o === "callvideo") updateCallVideo(false);
    if (!quiet) log(`setting ${o} → ${on ? "on" : "off"}`);
  }
  function applyAll() { for (const o of OPTS) if ($("opt-" + o).checked) apply(o, true, true); }

  // ── Save / copy / new run ──────────────────────────────
  async function saveLog(background) {
    const body = { run, device: store.get("lab.device", ""), settings: settingsNow(),
                   events: background ? events.slice(-400) : events };   // keepalive bodies are capped near 64 KB
    try {
      const res = await fetch("/teknix/log", {
        method: "POST", keepalive: background,
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify(body),
      });
      if (!background) $("send-msg").textContent = res.ok ? `Saved run ${run} (${events.length} lines).` : `Couldn't save (error ${res.status}).`;
    } catch (err) {
      if (!background) $("send-msg").textContent = "Couldn't save: " + err.message;
    }
  }

  // ── Wiring ─────────────────────────────────────────────
  $("device").value = store.get("lab.device", "");
  for (const o of OPTS) {
    const box = $("opt-" + o);
    box.checked = !!settings[o];
    box.addEventListener("change", () => {
      settings[o] = box.checked;
      store.set("lab.settings", settings);
      apply(o, box.checked);
    });
  }
  $("join").addEventListener("click", join);
  $("leave").addEventListener("click", () => leave());
  $("mic").addEventListener("click", toggleMic);
  $("tone").addEventListener("click", () => (tone ? stopTone() : startTone().catch((e) => log("beep failed: " + e.message))));
  $("pip").addEventListener("click", openPip);
  $("fullscreen").addEventListener("click", goFullscreen);
  $("send").addEventListener("click", () => saveLog(false));
  $("copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(events.join("\n")); $("send-msg").textContent = "Copied."; }
    catch (e) { $("send-msg").textContent = "Couldn't copy — use Save log instead."; }
  });
  $("clear").addEventListener("click", () => {
    run = newRunId();
    events = [];
    store.set("lab.run", run);
    renderLog();
    log(`new run ${run} — ${describeSettings()}`);
  });

  renderLog();
  log(`page loaded — run ${run} — ${describeSettings()}`);
  if ($("opt-video").checked) $("send-msg").textContent = "Tip: tap anywhere once so the keep-awake video can start.";
  document.addEventListener("pointerdown", () => { if ($("opt-video").checked && $("keepawake").paused) applyVideo(true); }, { once: true });
})();
