// arduino/relay_buzzer.ino
// Commands (newline-terminated):
//   ON                -> start continuous WAVE (ramps faster/slower until OFF)
//   OFF               -> stop everything, relay OFF
//   BEEP <ms>         -> single beep for <ms>
//   PULSE <ms> <cnt>  -> <cnt> beeps, each <ms> ON then <ms> OFF
//   LATCH             -> relay latched ON (steady)
//   QUIET             -> stop any pattern, relay OFF (alias of OFF)

#define RELAY_PIN 8
#define RELAY_ACTIVE_LOW 1  // 1 for most hobby relay modules (active when input LOW)

inline void relayOn()  { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? LOW  : HIGH); }
inline void relayOff() { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW ); }

// ------- state -------
enum Mode { IDLE, WAVE, PULSE, BEEPING, LATCHED };
Mode mode = IDLE;

bool relayState = false;
unsigned long nowMs, nextToggle = 0;

// BEEP (one-shot, non-blocking)
unsigned long beepOffAt = 0;

// PULSE (counted flicker)
unsigned long pulseInterval = 0;
int  pulseRemaining = 0;        // counts ON events remaining

// WAVE (continuous ramping)
int  waveMs   = 80;            // current interval
int  waveMin  = 80;            // fastest interval (lower = faster)
int  waveMax  = 80;            // slowest interval
int  waveStep = 80;             // how much to change interval each cycle
int  waveDir  = -1;             // -1 = speeding up, +1 = slowing down

void setRelay(bool on) {
  relayState = on;
  if (on) relayOn(); else relayOff();
}

void startWave() {
  mode = WAVE;
  // start from slow side and ramp faster
  waveMs  = waveMax;
  waveDir = -1;
  nextToggle = millis();     // toggle immediately to begin
}

void stopAll() {
  mode = IDLE;
  beepOffAt = 0;
  pulseRemaining = 0;
  nextToggle = 0;
  setRelay(false);
}

void startPulse(long ms, int count) {
  if (ms < 50)  ms = 200;
  if (count < 1) count = 3;
  pulseInterval = (unsigned long)ms;
  pulseRemaining = count;
  mode = PULSE;
  nextToggle = millis();  // start immediately
  setRelay(false);        // ensure OFF; first toggle will turn ON
}

void startBeep(long ms) {
  if (ms < 50) ms = 200;
  mode = BEEPING;
  setRelay(true);
  beepOffAt = millis() + (unsigned long)ms;
}

void latchOn() {
  mode = LATCHED;
  setRelay(true);
}

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);
  Serial.begin(9600);
}

void loop() {
  nowMs = millis();

  // ---- mode machines (non-blocking) ----

  // BEEP one-shot auto-off
  if (mode == BEEPING && beepOffAt && nowMs >= beepOffAt) {
    setRelay(false);
    beepOffAt = 0;
    mode = IDLE;
    Serial.println("OK BEEP DONE");
  }

  // PULSE counted
  if (mode == PULSE && nowMs >= nextToggle) {
    if (relayState) {
      // currently ON -> turn OFF and wait off gap
      setRelay(false);
      nextToggle = nowMs + pulseInterval;
    } else {
      // currently OFF -> if we still have pulses, turn ON
      if (pulseRemaining > 0) {
        setRelay(true);
        pulseRemaining--;
        nextToggle = nowMs + pulseInterval;
      } else {
        // finished
        mode = IDLE;
        setRelay(false);
        Serial.println("OK PULSE DONE");
      }
    }
  }

  // WAVE continuous (ramps interval between waveMax and waveMin)
  // pattern: ON for waveMs, OFF for waveMs, then adjust speed
  static bool wavePhaseOn = false;      // track ON/OFF phase in WAVE
  if (mode == WAVE && nowMs >= nextToggle) {
    wavePhaseOn = !wavePhaseOn;
    setRelay(wavePhaseOn);
    nextToggle = nowMs + (unsigned long)waveMs;

    // When completing an OFF phase (i.e., just turned OFF), adjust speed
    if (!wavePhaseOn) {
      waveMs += waveDir * waveStep;
      if (waveMs <= waveMin) { waveMs = waveMin; waveDir = +1; }
      if (waveMs >= waveMax) { waveMs = waveMax; waveDir = -1; }
    }
  }

  // ---- command handler ----
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim(); cmd.toUpperCase();

    if (cmd == "ON") {
      startWave();
      Serial.println("OK WAVE START");
    }
    else if (cmd == "OFF" || cmd == "QUIET") {
      stopAll();
      Serial.println("OK OFF");
    }
    else if (cmd.startsWith("BEEP")) {
      long ms = cmd.substring(4).toInt();
      startBeep(ms);
      Serial.println("OK BEEP");
    }
    else if (cmd.startsWith("PULSE")) {
      int sp = cmd.indexOf(' ', 5);
      long ms = cmd.substring(6, sp).toInt();
      int count = cmd.substring(sp + 1).toInt();
      startPulse(ms, count);
      Serial.println("OK PULSE START");
    }
    else if (cmd == "LATCH") {
      latchOn();
      Serial.println("OK LATCH");
    }
    else {
      Serial.println("ERR");
    }
  }
}
