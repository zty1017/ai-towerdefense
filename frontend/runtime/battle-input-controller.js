export function onBattleCanvasClick(context, event) {
  const battle = context.getBattle();
  if (!battle || battle.dialogueOpen || battle.finishing) return;
  const { cellFromCanvasEvent, deployToolAt } = context;
  const cell = cellFromCanvasEvent(event);
  if (cell) deployToolAt(battle.selectedTool, cell);
}

export function onBattleCanvasPointerMove(context, event) {
  const battle = context.getBattle();
  if (!battle || battle.dialogueOpen || battle.finishing) return;
  const { cellFromCanvasEvent } = context;
  battle.hoverCell = cellFromCanvasEvent(event);
}

export function onBattleCanvasPointerLeave(context) {
  const battle = context.getBattle();
  if (battle && !battle.draggingTool) {
    battle.hoverCell = null;
  }
}

export function beginToolDrag(context, tool, event) {
  const battle = context.getBattle();
  if (!battle || battle.dialogueOpen || battle.finishing) return;
  const { cellFromCanvasEvent, toolReady, toolUnavailableText, setBattleToast, updateBattleDom } = context;
  battle.selectedTool = tool || "basic";
  if (!toolReady(battle.selectedTool)) {
    battle.draggingTool = null;
    battle.dragPointer = null;
    battle.hoverCell = null;
    setBattleToast(toolUnavailableText(battle.selectedTool));
    updateBattleDom();
    event.preventDefault();
    return;
  }
  battle.draggingTool = battle.selectedTool;
  battle.dragPointer = { x: event.clientX, y: event.clientY };
  battle.hoverCell = cellFromCanvasEvent(event);
  updateBattleDom();
  event.preventDefault();
}

export function updateToolDrag(context, event) {
  const battle = context.getBattle();
  if (!battle || !battle.draggingTool) return;
  const { cellFromCanvasEvent } = context;
  battle.dragPointer = { x: event.clientX, y: event.clientY };
  battle.hoverCell = cellFromCanvasEvent(event);
  event.preventDefault();
}

export function finishToolDrag(context, event) {
  const battle = context.getBattle();
  if (!battle || !battle.draggingTool) return;
  const { cellFromCanvasEvent, deployToolAt, setBattleToast, updateBattleDom } = context;
  const tool = battle.draggingTool;
  const cell = cellFromCanvasEvent(event);
  battle.draggingTool = null;
  battle.dragPointer = null;
  battle.hoverCell = null;
  event.preventDefault();
  if (!cell) {
    setBattleToast("拖到战场格位后释放");
    updateBattleDom();
    return;
  }
  deployToolAt(tool, cell);
  updateBattleDom();
}

export function cancelToolDrag(context, event) {
  const battle = context.getBattle();
  if (!battle || !battle.draggingTool) return;
  const { updateBattleDom } = context;
  battle.draggingTool = null;
  battle.dragPointer = null;
  battle.hoverCell = null;
  if (event && typeof event.preventDefault === "function") event.preventDefault();
  updateBattleDom();
}
