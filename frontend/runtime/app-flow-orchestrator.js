export const PLAYER_VIEWS = Object.freeze([
  "loading",
  "profile",
  "world-config",
  "opening",
  "map",
  "workshop",
  "battle",
  "settlement",
]);

const SURFACE_TO_VIEW = Object.freeze({
  strategic_map: "map",
  prototype_workshop: "workshop",
  battle_canvas: "battle",
  settlement_panel: "settlement",
  opening_sequence: "opening",
});

export function createAppFlowOrchestrator({
  getView,
  setView,
  stopCurrentActivity,
  renderers,
  fallbackView = "profile",
} = {}) {
  const dependencies = { getView, setView, stopCurrentActivity };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createAppFlowOrchestrator requires ${name}`);
    }
  }
  const rendererMap = renderers && typeof renderers === "object" ? renderers : {};
  const knownViews = new Set(PLAYER_VIEWS);

  function normalizeView(view) {
    return knownViews.has(view) ? view : fallbackView;
  }

  function viewForSurface(surface) {
    return SURFACE_TO_VIEW[String(surface || "")] || null;
  }

  function setCurrentView(view) {
    const next = normalizeView(view);
    setView(next);
    return next;
  }

  function renderCurrent() {
    stopCurrentActivity();
    const current = normalizeView(getView());
    if (current !== getView()) setView(current);
    const renderer = rendererMap[current] || rendererMap[fallbackView];
    if (typeof renderer !== "function") {
      throw new Error(`No renderer registered for player view: ${current}`);
    }
    renderer();
    return current;
  }

  function navigate(view, { render = true } = {}) {
    const next = setCurrentView(view);
    if (render) renderCurrent();
    return next;
  }

  function navigateToSurface(surface, options) {
    const view = viewForSurface(surface);
    if (!view) return null;
    return navigate(view, options);
  }

  return {
    navigate,
    navigateToSurface,
    normalizeView,
    renderCurrent,
    setCurrentView,
    viewForSurface,
  };
}
