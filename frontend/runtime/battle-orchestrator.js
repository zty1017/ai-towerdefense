function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function runBattleUpdate({
  battle,
  dt,
  advanceBattleStep,
  onSampleDelivered,
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
  spawnEnemies({ battle });
  updateEnemies({ battle, dt });
  updateDefenses({ battle, dt });
  updateTraps({ battle, dt });
  updateEffects({ battle, dt });
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
