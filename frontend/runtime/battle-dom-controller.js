export function createBattleDomController({
  getBattle,
  ensureBattle,
  documentRef,
  windowRef,
  onCanvasClick,
  onCanvasPointerMove,
  onCanvasPointerLeave,
  computeMetrics,
  installSmokeProbe,
  preloadImages,
  shouldShowInitialDialogue,
  getInitialDialogue,
  resolvePortraitUrl,
  buildHudViewModel,
  renderToolbar,
  imageTag,
  safeText,
  startLoop,
  stopLoop,
} = {}) {
  const dependencies = {
    getBattle,
    ensureBattle,
    onCanvasClick,
    onCanvasPointerMove,
    onCanvasPointerLeave,
    computeMetrics,
    installSmokeProbe,
    preloadImages,
    shouldShowInitialDialogue,
    getInitialDialogue,
    resolvePortraitUrl,
    buildHudViewModel,
    renderToolbar,
    imageTag,
    safeText,
    startLoop,
    stopLoop,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleDomController requires ${name}`);
    }
  }
  if (!documentRef || !windowRef) {
    throw new TypeError("createBattleDomController requires documentRef and windowRef");
  }

  function battleDom() {
    return {
      shell: documentRef.querySelector(".battle-shell"),
      stats: documentRef.getElementById("battleStats"),
      tasks: documentRef.getElementById("battleTasks"),
      info: documentRef.getElementById("battleInfo"),
      tools: documentRef.getElementById("battleTools"),
      toast: documentRef.getElementById("battleToast"),
      dialogue: documentRef.getElementById("dialogueLayer"),
      pause: documentRef.getElementById("pauseButton"),
      speed: documentRef.getElementById("speedButton"),
    };
  }

  function resizeBattleCanvas() {
    const battle = getBattle();
    if (!battle || !battle.canvas || !battle.ctx) return;
    const canvas = battle.canvas;
    const rect = canvas.getBoundingClientRect();
    const dpr = windowRef.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    battle.ctx.imageSmoothingEnabled = true;
    battle.ctx.imageSmoothingQuality = "high";
    battle.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    battle.metrics = computeMetrics(rect.width, rect.height);
  }

  function setBattleToast(text) {
    const battle = getBattle();
    if (!battle) return;
    battle.toast = text;
    battle.toastUntil = battle.elapsedMs + 2200;
  }

  function showDialogue(name, line, portraitId) {
    const battle = getBattle();
    if (!battle || !battle.dom) return;
    battle.dialogueWasPaused = Boolean(battle.paused);
    battle.dialogueOpen = true;
    battle.paused = true;
    battle.draggingTool = null;
    battle.dragPointer = null;
    battle.hoverCell = null;
    if (battle.dom.shell) battle.dom.shell.classList.add("is-dialogue-open");
    const portrait = resolvePortraitUrl(portraitId);
    battle.dom.dialogue.innerHTML = `
      <div class="dialogue-overlay">
        <div class="dialogue-focus">
          <div class="portrait-slot">${imageTag(portrait, name)}</div>
          <div class="dialogue-box">
            <div class="dialogue-name">${safeText(name)}</div>
            <div class="dialogue-line">${safeText(line)}</div>
            <div class="screen-actions" style="margin-top:12px">
              <button class="primary-button" data-action="close-dialogue">继续</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function closeDialogue() {
    const battle = getBattle();
    if (!battle) return;
    battle.dialogueOpen = false;
    battle.paused = Boolean(battle.dialogueWasPaused);
    battle.dialogueWasPaused = false;
    if (battle.dom && battle.dom.shell) battle.dom.shell.classList.remove("is-dialogue-open");
    if (battle.dom && battle.dom.dialogue) battle.dom.dialogue.innerHTML = "";
    updateBattleDom();
  }

  function updateBattleDom() {
    const battle = getBattle();
    if (!battle || !battle.dom) return;
    const hud = buildHudViewModel();
    battle.dom.stats.innerHTML = hud.stats
      .map(
        (item) =>
          `<div class="top-stat"><span>${safeText(item.label)}</span><strong>${safeText(item.value)}</strong></div>`,
      )
      .join("");
    battle.dom.tasks.innerHTML = `
      <h2 class="panel-title">${safeText(hud.tasksTitle)}</h2>
      <div class="event-list">
        ${hud.taskItems
          .map(
            (item) =>
              `<div class="event-item"><strong>${safeText(item.title)}</strong><span>${safeText(item.text)}</span></div>`,
          )
          .join("")}
      </div>
    `;
    battle.dom.info.innerHTML = `
      <div class="side-avatar">${imageTag(hud.info.avatarUrl, hud.info.avatarAlt)}</div>
      <h2 class="panel-title">${safeText(hud.info.title)}</h2>
      <div class="event-list">
        ${hud.info.items
          .map(
            (item) =>
              `<div class="event-item"><strong>${safeText(item.title)}</strong><span>${safeText(item.text)}</span></div>`,
          )
          .join("")}
      </div>
    `;
    battle.dom.tools.innerHTML = renderToolbar(hud.toolbarTools);
    battle.dom.toast.textContent = hud.toastText;
    battle.dom.pause.textContent = hud.pauseText;
    battle.dom.speed.textContent = hud.speedText;
  }

  function setupBattle() {
    const canvas = documentRef.getElementById("battleCanvas");
    if (!canvas) return false;
    const ctx = canvas.getContext("2d");
    if (!ctx) return false;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    const battle = ensureBattle();
    Object.assign(battle, { canvas, ctx, dom: battleDom() });
    canvas.addEventListener("click", onCanvasClick);
    canvas.addEventListener("pointermove", onCanvasPointerMove);
    canvas.addEventListener("pointerleave", onCanvasPointerLeave);
    windowRef.addEventListener("resize", resizeBattleCanvas);
    resizeBattleCanvas();
    installSmokeProbe();
    preloadImages();
    if (shouldShowInitialDialogue()) {
      const dialogue = getInitialDialogue();
      showDialogue(dialogue.name, dialogue.line, dialogue.portraitId);
    }
    startLoop();
    return true;
  }

  function stopBattleLoop() {
    stopLoop();
    windowRef.removeEventListener("resize", resizeBattleCanvas);
  }

  function togglePause() {
    const battle = getBattle();
    if (!battle) return;
    battle.paused = !battle.paused;
    updateBattleDom();
  }

  function cycleSpeed() {
    const battle = getBattle();
    if (!battle) return;
    battle.speed = battle.speed === 1 ? 2 : battle.speed === 2 ? 0.5 : 1;
    updateBattleDom();
  }

  function selectTool(toolId) {
    const battle = getBattle();
    if (!battle) return;
    battle.selectedTool = toolId || "basic";
    updateBattleDom();
  }

  function announceMapLocked() {
    const battle = getBattle();
    if (!battle) return;
    battle.paused = true;
    setBattleToast("战斗中只能查看当前态势");
    updateBattleDom();
  }

  return {
    announceMapLocked,
    closeDialogue,
    cycleSpeed,
    resizeBattleCanvas,
    selectTool,
    setBattleToast,
    setupBattle,
    showDialogue,
    stopBattleLoop,
    togglePause,
    updateBattleDom,
  };
}
