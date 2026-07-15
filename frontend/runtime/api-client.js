function defaultTimerHost() {
  return globalThis.window || globalThis;
}

function defaultLocation() {
  return (globalThis.window && globalThis.window.location) || globalThis.location || { search: "" };
}

export async function fetchJson(url, options = {}, timeoutMs = 2400, deps = {}) {
  const Controller = deps.AbortController || globalThis.AbortController;
  const fetchImpl = deps.fetch || globalThis.fetch;
  const timerHost = deps.timerHost || defaultTimerHost();
  const controller = new Controller();
  const timer = timerHost.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } finally {
    timerHost.clearTimeout(timer);
  }
}

export function unwrapPayload(response) {
  return response && response.payload ? response.payload : response;
}

export function queryFlag(name, location = defaultLocation()) {
  const params = new URLSearchParams(location.search || "");
  if (!params.has(name)) return false;
  const value = String(params.get(name) || "1").toLowerCase();
  return !["0", "false", "no", "off"].includes(value);
}

export function queryParam(name, location = defaultLocation()) {
  const params = new URLSearchParams(location.search || "");
  return params.get(name);
}
