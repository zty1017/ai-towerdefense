function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function runBattleUpdate({
  battle,
  dt,
  advanceBattleStep,
  onSampleDelivered,
  onBattleEvents = () => {},
  spawnEnemies,
  updateEnemies,
  updateDefenses,
  updateTraps,
  updateEffects,
  resolveBattleOutcome,
  finishBattle,
}) {
  if (!battle || !battle.loopActive) return { updated: false, outcome: null };
  const step = advanceBattleStep({ battle, dt });
  if (step.sampleDelivered) onSampleDelivered({ battle, step });
  const events = {
    spawned: 0,
    kills: 0,
    leaks: 0,
    attack: false,
    trapTriggered: false,
  };
  const spawnedBefore = Number(battle.spawned || 0);
  spawnEnemies({ battle });
  events.spawned = Math.max(0, Number(battle.spawned || 0) - spawnedBefore);
  const killsBefore = Number(battle.kills || 0);
  const leaksBefore = Number(battle.leaks || 0);
  updateEnemies({ battle, dt });
  events.kills = Math.max(0, Number(battle.kills || 0) - killsBefore);
  events.leaks = Math.max(0, Number(battle.leaks || 0) - leaksBefore);
  const effectsBefore = Array.isArray(battle.effects) ? battle.effects.length : 0;
  updateDefenses({ battle, dt });
  events.attack = Boolean(
    Array.isArray(battle.effects)
      && battle.effects.slice(effectsBefore).some((effect) => effect && effect.type === "beam"),
  );
  const armedTrapsBefore = Array.isArray(battle.traps)
    ? battle.traps.filter((trap) => trap && trap.armed).length
    : 0;
  updateTraps({ battle, dt });
  events.trapTriggered = Boolean(
    Array.isArray(battle.traps)
      && battle.traps.filter((trap) => trap && trap.armed).length < armedTrapsBefore,
  );
  updateEffects({ battle, dt });
  if (Object.values(events).some(Boolean)) onBattleEvents({ battle, events });
  const outcome = resolveBattleOutcome({ battle });
  if (outcome) void finishBattle(outcome);
  return { updated: true, outcome, sampleDelivered: Boolean(step.sampleDelivered) };
}

export function createBattleOrchestrator({
  getBattle,
  requestFrame = (callback) => requestAnimationFrame(callback),
  cancelFrame = (frameId) => cancelAnimationFrame(frameId),
  isSimulationHeld = () => false,
  advanceBattleStep,
  onSampleDelivered = () => {},
  onBattleEvents = () => {},
  spawnEnemies,
  updateEnemies,
  updateDefenses,
  updateTraps,
  updateEffects,
  resolveBattleOutcome,
  finishBattle,
  drawBattle,
  updateBattleDom,
  maxFrameDeltaMs = 80,
  renderIntervalMs = 1000 / 30,
  domUpdateIntervalMs = 320,
} = {}) {
  if (typeof getBattle !== "function") {
    throw new TypeError("createBattleOrchestrator requires getBattle");
  }
  const requiredCallbacks = {
    advanceBattleStep,
    spawnEnemies,
    updateEnemies,
    updateDefenses,
    updateTraps,
    updateEffects,
    resolveBattleOutcome,
    finishBattle,
    drawBattle,
    updateBattleDom,
  };
  for (const [name, callback] of Object.entries(requiredCallbacks)) {
    if (typeof callback !== "function") {
      throw new TypeError(`createBattleOrchestrator requires ${name}`);
    }
  }

  let scheduledFrameId = null;
  let lastRenderAt = 0;

  function updateBattle(dt) {
    return runBattleUpdate({
      battle: getBattle(),
      dt,
      advanceBattleStep,
      onSampleDelivered,
      onBattleEvents,
      spawnEnemies,
      updateEnemies,
      updateDefenses,
      updateTraps,
      updateEffects,
      resolveBattleOutcome,
      finishBattle,
    });
  }

  function scheduleNextFrame() {
    scheduledFrameId = requestFrame(battleFrame);
  }

  function battleFrame(timestamp) {
    scheduledFrameId = null;
    const battle = getBattle();
    if (!battle || !battle.loopActive) return;
    if (!battle.lastFrameAt) battle.lastFrameAt = timestamp;
    const realDt = clamp(timestamp - battle.lastFrameAt, 0, maxFrameDeltaMs);
    battle.lastFrameAt = timestamp;
    const dt = battle.paused || isSimulationHeld() ? 0 : realDt * battle.speed;
    updateBattle(dt);
    if (!battle.loopActive || getBattle() !== battle) return;
    if (!lastRenderAt || timestamp - lastRenderAt >= renderIntervalMs) {
      drawBattle();
      lastRenderAt = timestamp;
    }
    if (battle.elapsedMs - battle.lastDomAt > domUpdateIntervalMs) {
      updateBattleDom();
      battle.lastDomAt = battle.elapsedMs;
    }
    scheduleNextFrame();
  }

  function start() {
    const battle = getBattle();
    if (!battle) return false;
    if (scheduledFrameId !== null) cancelFrame(scheduledFrameId);
    battle.loopActive = true;
    battle.lastFrameAt = 0;
    battle.lastDomAt = -999;
    lastRenderAt = 0;
    scheduleNextFrame();
    return true;
  }

  function stop() {
    const battle = getBattle();
    if (battle) battle.loopActive = false;
    if (scheduledFrameId !== null) cancelFrame(scheduledFrameId);
    scheduledFrameId = null;
  }

  return {
    battleFrame,
    start,
    stop,
    updateBattle,
  };
}
