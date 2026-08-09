const triggerMode      = document.getElementById('triggerMode');
const personConf       = document.getElementById('personConf');
const minPersonArea    = document.getElementById('minPersonArea');
const motionMinArea    = document.getElementById('motionMinArea');
const snapCooldown     = document.getElementById('snapCooldown');
const webcamIndex      = document.getElementById('webcamIndex');

const emailEnabled     = document.getElementById('emailEnabled');
const emailCooldown    = document.getElementById('emailCooldown');
const attachSnapshot   = document.getElementById('attachSnapshot');
const gmailAddr        = document.getElementById('gmailAddr');
const gmailPass        = document.getElementById('gmailPass');
const alertTo          = document.getElementById('alertTo');

const soundMode        = document.getElementById('soundMode');
const serialWrap       = document.getElementById('serialWrap');
const serialSelect     = document.getElementById('serialSelect');
const buzzerSerialPort = document.getElementById('buzzerSerialPort');
const applyPortBtn     = document.getElementById('applyPort');
const refreshPortsBtn  = document.getElementById('refreshPorts');
const portStatus       = document.getElementById('portStatus');

const buzzerHoldMs     = document.getElementById('buzzerHoldMs');

const saveConfigBtn    = document.getElementById('saveConfig');
const testEmailBtn     = document.getElementById('testEmail');
const testBuzzerBtn    = document.getElementById('testBuzzer');
const buzzOnBtn        = document.getElementById('buzzOn');
const buzzOffBtn       = document.getElementById('buzzOff');
const buzzBeepBtn      = document.getElementById('buzzBeep');
const bStatus          = document.getElementById('bStatus');

const toasts = document.getElementById('toasts');
function toast(msg){ if(!toasts) return; const d=document.createElement('div'); d.className='toast ok'; d.textContent=msg; toasts.appendChild(d); setTimeout(()=>d.remove(),1800); }

function showHideSerial(){ serialWrap.style.display = (soundMode.value === 'external' || soundMode.value === 'both') ? '' : 'none'; }

async function loadConfig(){
  const cfg = await (await fetch('/config')).json();

  triggerMode.value       = String(cfg.trigger_mode || 'person_only');
  personConf.value        = cfg.person_conf ?? 0.5;
  minPersonArea.value     = cfg.min_person_area_px ?? 2000;
  motionMinArea.value     = cfg.motion_min_area ?? 8000;
  snapCooldown.value      = cfg.snapshot_cooldown_sec ?? 8;
  webcamIndex.value       = cfg.webcam_index ?? 0;

  emailEnabled.value      = String(cfg.email_enabled ?? false);
  emailCooldown.value     = cfg.email_cooldown_sec ?? 30;
  attachSnapshot.checked  = !!cfg.attach_snapshot;
  gmailAddr.value         = cfg.GMAIL_ADDRESS || '';
  gmailPass.value         = cfg.GMAIL_APP_PASSWORD || '';
  alertTo.value           = cfg.ALERT_TO_EMAIL || '';

  soundMode.value         = String(cfg.sound_mode || 'external');
  buzzerSerialPort.value  = cfg.buzzer_serial_port || '';
  buzzerHoldMs.value      = cfg.buzzer_hold_ms ?? 2000;

  showHideSerial();
  refreshPorts();
  refreshBuzzerStatus();
}

async function refreshPorts(){
  try{
    const r = await fetch('/serial_ports');
    const d = await r.json();
    serialSelect.innerHTML = '';
    if(d.ok && Array.isArray(d.ports) && d.ports.length){
      for(const p of d.ports){
        const opt = document.createElement('option');
        opt.value = p; opt.textContent = p;
        serialSelect.appendChild(opt);
      }
      if (buzzerSerialPort.value){
        const match = Array.from(serialSelect.options).find(o => o.value === buzzerSerialPort.value);
        if (match) serialSelect.value = match.value;
      }
    }else{
      const opt = document.createElement('option'); opt.value=''; opt.textContent='(No ports found)';
      serialSelect.appendChild(opt);
    }
  }catch(e){
    const opt = document.createElement('option'); opt.value=''; opt.textContent='(pyserial not available)';
    serialSelect.appendChild(opt);
  }
}

applyPortBtn?.addEventListener('click', async ()=>{
  const port = (serialSelect.value || buzzerSerialPort.value || '').trim();
  if(!port){ portStatus.textContent = 'No port selected'; return; }
  buzzerSerialPort.value = port;
  await fetch('/set_port', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ port }) });
  portStatus.textContent = `Port set to ${port}`;
  toast('Port applied ✓');
  setTimeout(refreshBuzzerStatus, 300);
});

refreshPortsBtn?.addEventListener('click', refreshPorts);

saveConfigBtn.addEventListener('click', async ()=>{
  const payload = {
    trigger_mode: triggerMode.value,
    use_yolo: triggerMode.value === 'person_only',
    person_conf: Number(personConf.value || 0.5),
    min_person_area_px: Number(minPersonArea.value || 2000),
    motion_min_area: Number(motionMinArea.value || 8000),
    snapshot_cooldown_sec: Number(snapCooldown.value || 8),
    webcam_index: Number(webcamIndex.value || 0),

    email_enabled: (emailEnabled.value === 'true'),
    email_cooldown_sec: Number(emailCooldown.value || 30),
    attach_snapshot: !!attachSnapshot.checked,
    GMAIL_ADDRESS: gmailAddr.value.trim(),
    GMAIL_APP_PASSWORD: gmailPass.value.trim(),
    ALERT_TO_EMAIL: (alertTo.value.trim() || gmailAddr.value.trim()),

    sound_mode: soundMode.value,
    buzzer_serial_port: buzzerSerialPort.value.trim(),
    buzzer_hold_ms: Number(buzzerHoldMs.value || 2000),
  };
  await fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  toast('Settings saved ✓');
});

testEmailBtn?.addEventListener('click', async ()=>{
  const res = await fetch('/email_test', { method:'POST' });
  const data = await res.json();
  if (data.ok) toast('Test email sent ✓'); else toast('Email failed: ' + (data.message||'error'));
});

testBuzzerBtn?.addEventListener('click', async ()=>{
  const res = await fetch('/buzzer_test', { method:'POST' });
  const data = await res.json();
  if (data.ok) { toast('Pulse ✓'); refreshBuzzerStatus(); } else toast('Pulse failed: ' + (data.error||'error'));
});

buzzOnBtn?.addEventListener('click', async ()=>{
  await fetch('/buzzer_on', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ ms: Number(buzzerHoldMs.value || 2000) }) });
  toast('ON ✓'); setTimeout(refreshBuzzerStatus, 200);
});

buzzOffBtn?.addEventListener('click', async ()=>{
  await fetch('/buzzer_off', { method:'POST' });
  toast('OFF ✓'); setTimeout(refreshBuzzerStatus, 200);
});

buzzBeepBtn?.addEventListener('click', async ()=>{
  await fetch('/buzzer_beep', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ ms: 800 }) });
  toast('BEEP ✓'); setTimeout(refreshBuzzerStatus, 200);
});

soundMode.addEventListener('change', showHideSerial);

async function refreshBuzzerStatus(){
  try{
    const r = await fetch('/buzzer_status');
    const d = await r.json();
    bStatus.textContent = `Port: ${d.port || '—'} • State: ${d.is_on ? 'ON' : 'OFF'}`;
  }catch{ bStatus.textContent = '—'; }
}

loadConfig();
