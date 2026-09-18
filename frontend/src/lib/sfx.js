// frontend/src/lib/sfx.js
// Tiny 8-bit / chiptune sound engine built on the Web Audio API.
//
// No audio files to download and nothing to license: every sound is synthesised
// from square/sawtooth oscillators with a short attack/decay envelope, which is
// exactly how classic 8-bit consoles produced their blips.

let ctx = null;
let enabled = false;
let loaded = false;

// Each sound is a list of notes: f = frequency (Hz), t = start offset (s),
// d = duration (s), type = oscillator wave, g = peak gain (0..1).
const SOUNDS = {
  click: [{ f: 440, t: 0, d: 0.05, type: 'square', g: 0.12 }],

  pop: [
    { f: 660, t: 0, d: 0.04, type: 'square', g: 0.12 },
    { f: 880, t: 0.04, d: 0.05, type: 'square', g: 0.10 },
  ],

  back: [
    { f: 520, t: 0, d: 0.04, type: 'square', g: 0.10 },
    { f: 330, t: 0.04, d: 0.06, type: 'square', g: 0.10 },
  ],

  success: [
    { f: 523, t: 0, d: 0.08, type: 'square', g: 0.11 },
    { f: 659, t: 0.08, d: 0.08, type: 'square', g: 0.11 },
    { f: 784, t: 0.16, d: 0.16, type: 'square', g: 0.12 },
  ],

  save: [
    { f: 392, t: 0, d: 0.06, type: 'square', g: 0.11 },
    { f: 523, t: 0.06, d: 0.10, type: 'square', g: 0.11 },
  ],

  error: [
    { f: 220, t: 0, d: 0.10, type: 'sawtooth', g: 0.10 },
    { f: 165, t: 0.10, d: 0.18, type: 'sawtooth', g: 0.10 },
  ],

  coin: [
    { f: 988, t: 0, d: 0.06, type: 'square', g: 0.11 },
    { f: 1319, t: 0.06, d: 0.16, type: 'square', g: 0.11 },
  ],

  fanfare: [
    { f: 523, t: 0, d: 0.07, type: 'square', g: 0.11 },
    { f: 659, t: 0.07, d: 0.07, type: 'square', g: 0.11 },
    { f: 784, t: 0.14, d: 0.07, type: 'square', g: 0.11 },
    { f: 1047, t: 0.21, d: 0.22, type: 'square', g: 0.12 },
  ],
};

function ensureCtx() {
  if (typeof window === 'undefined') return null;
  if (!ctx) {
    const AudioCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtor) return null;
    try {
      ctx = new AudioCtor();
    } catch {
      return null;
    }
  }
  // Browsers start the context suspended until a user gesture; resume on demand.
  if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
}

/** Play one of the named 8-bit sounds. No-op when sound is disabled. */
export function playSfx(name) {
  if (!enabled) return;
  const spec = SOUNDS[name];
  if (!spec) return;
  const ac = ensureCtx();
  if (!ac) return;

  const now = ac.currentTime;
  for (const note of spec) {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = note.type || 'square';
    osc.frequency.setValueAtTime(note.f, now + note.t);

    // Exponential ramps sound closer to real hardware than a flat gate,
    // but they cannot ramp to exactly 0, hence the tiny floor value.
    const peak = note.g ?? 0.1;
    gain.gain.setValueAtTime(0.0001, now + note.t);
    gain.gain.exponentialRampToValueAtTime(peak, now + note.t + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + note.t + note.d);

    osc.connect(gain).connect(ac.destination);
    osc.start(now + note.t);
    osc.stop(now + note.t + note.d + 0.02);
  }
}

/** Turn sound on/off at runtime (used by the Preferences toggle). */
export function setSfxEnabled(value) {
  enabled = !!value;
  if (enabled) ensureCtx();
  return enabled;
}

export function isSfxEnabled() {
  return enabled;
}

/** Read the saved preference from the backend once and cache it. */
export async function loadSfxSetting() {
  if (loaded) return enabled;
  loaded = true;
  try {
    const res = await fetch('/api/v1/settings');
    if (res.ok) {
      const data = await res.json();
      enabled = !!data.sfx;
    }
  } catch {
    // Offline or backend down: stay silent rather than crash the UI.
  }
  return enabled;
}

export default playSfx;
