export function createRootEventRouter(options = {}) {
  const {
    root,
    windowRef,
    actionHandlers = {},
    isActionBlocked = () => false,
    getSuppressMapClick = () => false,
    setSuppressMapClick = () => {},
    canBeginToolDrag = () => false,
  } = options;
  if (!root || !windowRef) throw new TypeError("createRootEventRouter requires root and windowRef");
  const callbacks = [
    "beginToolDrag",
    "updateToolDrag",
    "finishToolDrag",
    "cancelToolDrag",
    "beginStrategicMapDrag",
    "updateStrategicMapDrag",
    "finishStrategicMapDrag",
    "handleStrategicMapWheel",
    "updateIntent",
  ];
  for (const name of callbacks) {
    if (typeof options[name] !== "function") {
      throw new TypeError(`createRootEventRouter requires ${name}`);
    }
  }

  function dispatchAction(action, target) {
    if (!action || isActionBlocked(action, target)) return false;
    const handler = actionHandlers[action];
    if (typeof handler !== "function") return false;
    handler(target);
    return true;
  }

  function onClick(event) {
    const map = event.target.closest && event.target.closest(".strategic-map");
    if (getSuppressMapClick() && map) {
      setSuppressMapClick(false);
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    setSuppressMapClick(false);
    const target = event.target.closest && event.target.closest("[data-action]");
    if (!target) return;
    event.preventDefault();
    dispatchAction(target.dataset.action, target);
  }

  function onPointerDown(event) {
    const target = event.target.closest && event.target.closest(".toolbar-card[data-tool]");
    if (target) {
      if (canBeginToolDrag(event, target)) options.beginToolDrag(target.dataset.tool, event);
      return;
    }
    options.beginStrategicMapDrag(event);
  }

  function onWheel(event) {
    if (!options.handleStrategicMapWheel(event)) return;
    event.preventDefault();
  }

  function onInput(event) {
    const target = event.target;
    if (target && target.dataset && target.dataset.field === "intent") {
      options.updateIntent(target.value, target);
    }
  }

  let installed = false;
  function install() {
    if (installed) return;
    installed = true;
    root.addEventListener("click", onClick);
    root.addEventListener("pointerdown", onPointerDown);
    root.addEventListener("wheel", onWheel, { passive: false });
    root.addEventListener("input", onInput);
    windowRef.addEventListener("pointermove", options.updateToolDrag);
    windowRef.addEventListener("pointerup", options.finishToolDrag);
    windowRef.addEventListener("pointercancel", options.cancelToolDrag);
    windowRef.addEventListener("pointermove", options.updateStrategicMapDrag);
    windowRef.addEventListener("pointerup", options.finishStrategicMapDrag);
    windowRef.addEventListener("pointercancel", options.finishStrategicMapDrag);
  }

  function uninstall() {
    if (!installed) return;
    installed = false;
    root.removeEventListener("click", onClick);
    root.removeEventListener("pointerdown", onPointerDown);
    root.removeEventListener("wheel", onWheel, { passive: false });
    root.removeEventListener("input", onInput);
    windowRef.removeEventListener("pointermove", options.updateToolDrag);
    windowRef.removeEventListener("pointerup", options.finishToolDrag);
    windowRef.removeEventListener("pointercancel", options.cancelToolDrag);
    windowRef.removeEventListener("pointermove", options.updateStrategicMapDrag);
    windowRef.removeEventListener("pointerup", options.finishStrategicMapDrag);
    windowRef.removeEventListener("pointercancel", options.finishStrategicMapDrag);
  }

  return { dispatchAction, install, uninstall };
}
