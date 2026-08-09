// ---------- mode & elements ----------
const mode = document.body?.dataset?.mode || 'live';

const statusPill = document.getElementById('status-pill');
const videoImg   = document.getElementById('video');
const eventsDiv  = document.getElementById('events');

const startBtn   = document.getElementById('startBtn');
const stopBtn    = document.getElementById('stopBtn');
const silenceBtn = document.getElementById('silenceBtn');

const videoFile      = document.getElementById('videoFile');
const uploadVideoBtn = document.getElementById('uploadVideoBtn');

const videoProgress = document.getElementById('videoProgress');
const videoBar      = videoProgress?.querySelector('.bar');
const videoCard     = document.getElementById('videoCard');
const vName         = document.getElementById('vName');
const vSub          = document.getElementById('vSub');

const toasts = document.getElementById('toasts');

// ---------- helpers ----------
function toast(msg, type = 'ok') {
  if (!toasts) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  toasts.appendChild(el);
  // smooth auto-remove
  setTimeout(() => {
    try { el.remove(); } catch {}
  }, 2200);
}

function prettyBytes(bytes) {
  if (!bytes) return '—';
  const k = 1024, u = ['B','KB','MB','GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${u[i]}`;
}
function fmtDur(sec) {
  if (!isFinite(sec)) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

async function withBtnBusy(btn, fn) {
  if (!btn) return fn();
  btn.disabled = true;
  try { return await fn(); }
  finally { btn.disabled = false; }
}

function setStatus(running) {
  const pill = statusPill;
  if (!pill) return;
  pill.textContent = running ? '● Running' : '● Idle';
  pill.classList.toggle('ok', !!running);
}

// ---------- upload demo video ----------
uploadVideoBtn?.addEventListener('click', () => {
  if (!videoFile?.files?.length) return alert('Pick a video first');
  const file = videoFile.files[0];

  // Show metadata preview
  const url = URL.createObjectURL(file);
  const v = document.createElement('video');
  v.preload = 'metadata'; v.src = url;
  v.onloadedmetadata = () => {
    if (vName) vName.textContent = file.name;
    if (vSub)  vSub.textContent  = `${v.videoWidth}×${v.videoHeight} • ${fmtDur(v.duration)} • ${prettyBytes(file.size)} • ${file.type || 'video'}`;
    if (videoCard) videoCard.hidden = false;
    URL.revokeObjectURL(url);
  };

  const fd = new FormData(); fd.append('video', file);
  const xhr = new XMLHttpRequest(); xhr.open('POST','/upload_video',true);

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable && videoProgress && videoBar) {
      videoProgress.hidden = false;
      videoBar.style.width = `${(e.loaded / e.total) * 100}%`;
    }
  };
  xhr.onload = () => {
    if (videoProgress) videoProgress.hidden = true;
    if (xhr.status === 200) {
      try {
        const d = JSON.parse(xhr.responseText);
        if (d.ok) {
          window.__CURRENT_VIDEO_PATH__ = d.path;
          toast('Video uploaded ✓', 'ok');
        } else {
          toast('Upload failed', 'err');
        }
      } catch {
        toast('Upload failed', 'err');
      }
    } else {
      toast('Upload failed', 'err');
    }
  };
  xhr.onerror = () => {
    if (videoProgress) videoProgress.hidden = true;
    toast('Upload error', 'err');
  };
  xhr.send(fd);
});

// ---------- frame polling ----------
let pollTimer = null;
function startPoll(fps = 8) {
  stopPoll();
  const interval = Math.max(60, Math.round(1000 / fps));
  pollTimer = setInterval(() => {
    videoImg.src = `/frame.jpg?bust=${Date.now()}`;
  }, interval);
  setStatus(true);
}
function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// Start slow poll on load so users see “idle”/blank canvas nicely
window.addEventListener('DOMContentLoaded', () => startPoll(4));

// ---------- start/stop buttons ----------
startBtn?.addEventListener('click', () => withBtnBusy(startBtn, async () => {
  const payload = (mode === 'live')
    ? { source: 'webcam' }
    : { source: 'file', video_path: window.__CURRENT_VIDEO_PATH__ };

  if (mode !== 'live' && !window.__CURRENT_VIDEO_PATH__)
    return alert('Upload a video first');

  const res = await fetch('/start', {
    method: 'POST',
    headers: { 'Content-Type':'application/json' },
    body: JSON.stringify(payload)
  });

  let ok = false, err = '';
  try {
    const data = await res.json();
    ok = !!data.ok; err = data.error || '';
  } catch {}

  if (!ok) {
    toast(`Failed to start${err ? ': ' + err : ''}`, 'err');
    return;
  }

  startPoll(8);
  connectEvents();  // begin SSE stream after we’re running
  toast('Started ✓', 'ok');
}));

stopBtn?.addEventListener('click', () => withBtnBusy(stopBtn, async () => {
  stopPoll();
  if (videoImg) videoImg.src = '';
  try { await fetch('/stop', { method:'POST' }); } catch {}
  setStatus(false);
  toast('Stopped', 'info');
}));

silenceBtn?.addEventListener('click', async () => {
  try {
    await fetch('/buzzer_off', { method:'POST' });
    toast('Siren silenced', 'ok');
  } catch {
    toast('Failed to silence', 'err');
  }
});

// ---------- SSE events (intrusions / heartbeat) ----------
let sse = null;
function connectEvents() {
  if (sse) { try { sse.close(); } catch {} sse = null; }

  sse = new EventSource('/events');

  sse.onmessage = (evt) => {
    try {
      const e = JSON.parse(evt.data);
      if (e.type === 'intrusion') onIntrusion(e);
      if (e.type === 'heartbeat') setStatus(true);
    } catch {}
  };

  sse.onerror = () => {
    try { sse.close(); } catch {}
    sse = null;
    // Try reconnecting gently
    setTimeout(connectEvents, 1000);
  };
}

function onIntrusion(e) {
  // Event list
  const ts = new Date((e.ts || Date.now()/1000) * 1000).toLocaleString();
  const link = e.snapshot_url ? `<a href="/${e.snapshot_url.replace(/^\//,'')}" target="_blank">snapshot</a>` : '';
  const row = document.createElement('div');
  row.innerHTML = `🔴 Intrusion at <b>${ts}</b> ${link}`;
  if (eventsDiv) {
    eventsDiv.prepend(row);
    while (eventsDiv.children.length > 10) {
      eventsDiv.removeChild(eventsDiv.lastChild);
    }
  }

  // Visual pulse on frame
  videoImg?.classList.add('flash');
  setTimeout(() => videoImg?.classList.remove('flash'), 1000);
}

// Optional: clean up on page unload
window.addEventListener('beforeunload', () => {
  try { if (sse) sse.close(); } catch {}
  stopPoll();
});
