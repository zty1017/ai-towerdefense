const STORAGE_KEY = "ai_compiled_td_audio_muted_v1";

const SCENE_PATTERNS = {
  profile: { notes: [110, 146.83, 164.81], stepMs: 1900, gain: 0.026 },
  "world-config": { notes: [110, 164.81, 220], stepMs: 1700, gain: 0.027 },
  opening: { notes: [98, 130.81, 146.83], stepMs: 2100, gain: 0.03 },
  map: { notes: [110, 146.83, 196, 164.81], stepMs: 1650, gain: 0.028 },
  workshop: { notes: [130.81, 164.81, 196, 261.63], stepMs: 1250, gain: 0.026 },
  battle: { notes: [98, 146.83, 174.61, 196], stepMs: 760, gain: 0.032 },
  settlement: { notes: [130.81, 164.81, 220, 261.63], stepMs: 1800, gain: 0.03 },
};

const SFX_THROTTLE_MS = {
  attack: 115,
  impact: 90,
  kill: 120,
  ui: 45,
};

function resolveAudioContext(windowRef) {
  return windowRef && (windowRef.AudioContext || windowRef.webkitAudioContext);
}

function readMuted(storage) {
  try {
    return storage && storage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeMuted(storage, muted) {
  try {
    if (storage) storage.setItem(STORAGE_KEY, muted ? "1" : "0");
  } catch {
    // Audio preference persistence is optional.
  }
}

export function createAudioDirector({
  windowRef = globalThis.window,
  documentRef = globalThis.document,
  storage = globalThis.localStorage,
  createContext = null,
  musicByScene = {},
  createMediaElement = null,
} = {}) {
  let context = null;
  let masterGain = null;
  let musicGain = null;
  let sfxGain = null;
  let patternTimer = null;
  let scene = "profile";
  let noteIndex = 0;
  let muted = readMuted(storage);
  let unlockPromise = null;
  let activeMusic = null;
  let activeMusicUrl = "";
  const lastPlayedAt = new Map();
  const musicElements = new Map();

  function mediaElement(url) {
    if (!url) return null;
    if (musicElements.has(url)) return musicElements.get(url);
    const element = createMediaElement
      ? createMediaElement(url)
      : windowRef && typeof windowRef.Audio === "function"
        ? new windowRef.Audio(url)
        : null;
    if (!element) return null;
    element.loop = true;
    element.preload = "auto";
    element.volume = 0.2;
    element.muted = muted;
    musicElements.set(url, element);
    return element;
  }

  async function syncFileMusic() {
    const url = musicByScene[scene] || "";
    if (!url) {
      if (activeMusic && typeof activeMusic.pause === "function") activeMusic.pause();
      activeMusic = null;
      activeMusicUrl = "";
      return false;
    }
    const nextMusic = mediaElement(url);
    if (!nextMusic) return false;
    if (activeMusic && activeMusic !== nextMusic && typeof activeMusic.pause === "function") {
      activeMusic.pause();
    }
    activeMusic = nextMusic;
    activeMusicUrl = url;
    activeMusic.muted = muted;
    if (muted) return true;
    try {
      const playback = activeMusic.play && activeMusic.play();
      if (playback && typeof playback.then === "function") await playback;
      return true;
    } catch {
      activeMusic = null;
      activeMusicUrl = "";
      return false;
    }
  }

  function applyMuteState() {
    for (const element of musicElements.values()) element.muted = muted;
    if (context && masterGain) {
      const now = context.currentTime;
      masterGain.gain.cancelScheduledValues(now);
      masterGain.gain.setTargetAtTime(muted ? 0 : 0.72, now, 0.025);
    }
  }

  function makeBus(value) {
    const bus = context.createGain();
    bus.gain.value = value;
    bus.connect(masterGain);
    return bus;
  }

  function tone({ frequency, duration = 0.22, gain = 0.035, type = "sine", delay = 0, bus = sfxGain }) {
    if (!context || !bus || muted) return;
    const start = context.currentTime + delay;
    const oscillator = context.createOscillator();
    const envelope = context.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(Math.max(24, frequency), start);
    envelope.gain.setValueAtTime(0.0001, start);
    envelope.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), start + 0.018);
    envelope.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    oscillator.connect(envelope);
    envelope.connect(bus);
    oscillator.start(start);
    oscillator.stop(start + duration + 0.03);
  }

  function tickPattern() {
    const pattern = SCENE_PATTERNS[scene] || SCENE_PATTERNS.map;
    if (activeMusic && activeMusicUrl === musicByScene[scene] && !activeMusic.paused) return;
    if (!context || muted || context.state !== "running") return;
    const root = pattern.notes[noteIndex % pattern.notes.length];
    noteIndex += 1;
    tone({
      frequency: root,
      duration: scene === "battle" ? 0.42 : 1.45,
      gain: pattern.gain,
      type: scene === "battle" ? "triangle" : "sine",
      bus: musicGain,
    });
    tone({
      frequency: root * 1.5,
      duration: scene === "battle" ? 0.22 : 1.1,
      gain: pattern.gain * 0.34,
      type: "sine",
      delay: scene === "battle" ? 0.17 : 0.08,
      bus: musicGain,
    });
  }

  function restartPattern() {
    if (patternTimer !== null && windowRef) windowRef.clearInterval(patternTimer);
    patternTimer = null;
    noteIndex = 0;
    if (!context || !windowRef) return;
    tickPattern();
    const pattern = SCENE_PATTERNS[scene] || SCENE_PATTERNS.map;
    patternTimer = windowRef.setInterval(tickPattern, pattern.stepMs);
  }

  async function unlock() {
    if (context) {
      if (context.state === "suspended" && typeof context.resume === "function") await context.resume();
      await syncFileMusic();
      return true;
    }
    if (unlockPromise) return unlockPromise;
    unlockPromise = (async () => {
      const Context = createContext || resolveAudioContext(windowRef);
      if (Context) {
        context = typeof Context === "function" ? new Context() : Context;
        masterGain = context.createGain();
        masterGain.gain.value = muted ? 0 : 0.72;
        masterGain.connect(context.destination);
        musicGain = makeBus(0.62);
        sfxGain = makeBus(0.88);
        if (context.state === "suspended" && typeof context.resume === "function") await context.resume();
      }
      const hasFileMusic = await syncFileMusic();
      if (!context && !hasFileMusic) return false;
      restartPattern();
      return true;
    })();
    try {
      return await unlockPromise;
    } finally {
      unlockPromise = null;
    }
  }

  function shouldPlay(kind) {
    const throttle = SFX_THROTTLE_MS[kind] || 0;
    const now = Date.now();
    if (now - Number(lastPlayedAt.get(kind) || 0) < throttle) return false;
    lastPlayedAt.set(kind, now);
    return true;
  }

  async function play(kind) {
    if (muted || !shouldPlay(kind)) return false;
    if (!(await unlock())) return false;
    const sounds = {
      ui: () => tone({ frequency: 392, duration: 0.07, gain: 0.022, type: "triangle" }),
      deploy: () => {
        tone({ frequency: 116.54, duration: 0.16, gain: 0.07, type: "triangle" });
        tone({ frequency: 233.08, duration: 0.22, gain: 0.045, type: "sine", delay: 0.055 });
      },
      trap: () => {
        tone({ frequency: 261.63, duration: 0.18, gain: 0.04, type: "sine" });
        tone({ frequency: 392, duration: 0.28, gain: 0.035, type: "triangle", delay: 0.08 });
      },
      support: () => {
        tone({ frequency: 196, duration: 0.34, gain: 0.05, type: "sine" });
        tone({ frequency: 293.66, duration: 0.42, gain: 0.038, type: "sine", delay: 0.07 });
      },
      attack: () => tone({ frequency: 523.25, duration: 0.085, gain: 0.026, type: "square" }),
      impact: () => tone({ frequency: 92.5, duration: 0.1, gain: 0.042, type: "triangle" }),
      kill: () => tone({ frequency: 73.42, duration: 0.16, gain: 0.052, type: "sawtooth" }),
      leak: () => {
        tone({ frequency: 174.61, duration: 0.28, gain: 0.055, type: "sawtooth" });
        tone({ frequency: 116.54, duration: 0.3, gain: 0.045, type: "sawtooth", delay: 0.12 });
      },
      wave: () => {
        tone({ frequency: 98, duration: 0.42, gain: 0.06, type: "triangle" });
        tone({ frequency: 146.83, duration: 0.32, gain: 0.04, type: "triangle", delay: 0.16 });
      },
      sample_ready: () => {
        [261.63, 329.63, 392].forEach((frequency, index) =>
          tone({ frequency, duration: 0.42, gain: 0.042, type: "sine", delay: index * 0.1 }),
        );
      },
      victory: () => {
        [196, 246.94, 293.66, 392].forEach((frequency, index) =>
          tone({ frequency, duration: 0.65, gain: 0.052, type: "triangle", delay: index * 0.14 }),
        );
      },
      defeat: () => {
        [196, 164.81, 130.81, 98].forEach((frequency, index) =>
          tone({ frequency, duration: 0.58, gain: 0.045, type: "sawtooth", delay: index * 0.15 }),
        );
      },
    };
    const sound = sounds[kind];
    if (!sound) return false;
    sound();
    return true;
  }

  function setScene(nextScene) {
    scene = SCENE_PATTERNS[nextScene] ? nextScene : "map";
    if (context || activeMusic) {
      void syncFileMusic().finally(() => restartPattern());
    }
  }

  async function toggleMuted() {
    muted = !muted;
    writeMuted(storage, muted);
    if (!muted) await unlock();
    applyMuteState();
    if (!muted) {
      await syncFileMusic();
      restartPattern();
    }
    return muted;
  }

  function controlLabel() {
    return muted ? "开启声音" : "静音";
  }

  function bindUnlockEvents() {
    if (!documentRef || typeof documentRef.addEventListener !== "function") return;
    const onIntent = () => void unlock();
    documentRef.addEventListener("pointerdown", onIntent, { passive: true });
    documentRef.addEventListener("keydown", onIntent);
    documentRef.addEventListener("click", (event) => {
      const target = event && event.target;
      if (target && typeof target.closest === "function" && target.closest("button")) void play("ui");
    });
  }

  bindUnlockEvents();

  return {
    controlLabel,
    isMuted: () => muted,
    play,
    setScene,
    toggleMuted,
    unlock,
  };
}
