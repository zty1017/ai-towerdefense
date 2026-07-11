export function createOnboardingFeatureController({
  root,
  getState,
  getWorldConfig,
  defaultWorldConfig,
  screenHeader,
  safeText,
  getProfilePreviewUrl = () => "",
  getWorldPreviewUrl = () => "",
  getOpeningSceneUrl = () => "",
  navigate,
  renderApp,
} = {}) {
  const dependencies = {
    getState,
    getWorldConfig,
    screenHeader,
    safeText,
    navigate,
    renderApp,
  };
  if (!root) throw new TypeError("createOnboardingFeatureController requires root");
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createOnboardingFeatureController requires ${name}`);
    }
  }

  function renderProfile() {
    const state = getState();
    const hasSession = Boolean(state.sessionId || state.profile.sessionId);
    const previewUrl = getProfilePreviewUrl();
    root.innerHTML = `
      <main class="screen">
        <section class="hero-layout">
          <div>
            <div class="eyebrow">本地档案</div>
            <h1 class="screen-title">余灯中枢</h1>
            <p class="screen-subtitle">
              长夜未尽，灰灯驿站发来急报。档案只保存在本机，进入后会为本次体验建立独立进度。
            </p>
            <div class="profile-menu" style="margin-top:24px">
              <button class="menu-button primary-button" data-action="continue">
                <span><strong>${hasSession ? "继续当前体验" : "开始新档案"}</strong><span>从开局配置进入第一场危机</span></span>
                <b>›</b>
              </button>
              <button class="menu-button" data-action="new-archive">
                <span><strong>开始新档案</strong><span>清空本机演示进度</span></span>
                <b>↻</b>
              </button>
              <button class="menu-button ghost-button" data-action="reset-demo">
                <span><strong>重置演示</strong><span>保留入口，重新生成本次进度</span></span>
                <b>⌁</b>
              </button>
              <button class="menu-button ghost-button" data-action="settings">
                <span><strong>设置</strong><span>${state.dataMode === "api" ? "中枢档案已连通" : "使用本机档案"}</span></span>
                <b>⚙</b>
              </button>
            </div>
          </div>
          <div class="profile-visual" aria-label="余灯中枢远景">
            ${previewUrl ? `<img src="${safeText(previewUrl)}" alt="余灯中枢与周边前线态势" loading="eager" />` : ""}
            <div class="profile-visual-caption">
              <span>前线急报</span>
              <strong>灰灯驿站信标正在熄灭</strong>
              <small>建立本局世界后，地图、任务与可研发装置将随局势生长。</small>
            </div>
          </div>
        </section>
      </main>
    `;
  }

  function renderWorldConfig() {
    const state = getState();
    const config = getWorldConfig();
    const creativity = config.creativity_mode || defaultWorldConfig.creativity_mode;
    const origin = config.player_origin || defaultWorldConfig.player_origin;
    const previewUrl = getWorldPreviewUrl();
    root.innerHTML = `
      <main class="screen">
        ${screenHeader("建立本局档案", "选择本局世界书、画风、创造性与开局身份。", "开局建档")}
        <section class="config-grid">
          <aside class="panel">
            <h2 class="panel-title">世界书</h2>
            <p class="panel-text">${safeText(config.worldbook_display_name || "长夜灯火")}</p>
            <div class="tag-row">
              <span class="tag">灯火</span>
              <span class="tag">影潮</span>
              <span class="tag">前哨</span>
            </div>
            <p class="panel-text">长夜没有结束，余灯中枢仍在燃烧。第一处危机已经点亮。</p>
          </aside>
          <div class="world-preview" aria-label="画风预览">
            ${previewUrl ? `<img src="${safeText(previewUrl)}" alt="当前世界画风下的灰灯驿站战场" loading="eager" />` : ""}
            <div class="world-preview-caption">
              <div class="eyebrow">画风</div>
              <h2 class="panel-title">${safeText(config.visual_style_display_name || "灯塬旧朝·伪三维")}</h2>
              <p class="panel-text">斜视角战场、暗色地形、暖金灯火与冷色迟滞场。</p>
            </div>
          </div>
          <aside class="panel">
            <h2 class="panel-title">创造性</h2>
            <div class="option-stack">
              ${(creativity.options || [])
                .map(
                  (option) => `
                    <button class="option-button ${state.selectedOptions.creativity_mode === option.id ? "is-selected" : ""}" data-action="select-creativity" data-value="${safeText(option.id)}">
                      <strong>${safeText(option.display_name)}</strong>
                      <span>${safeText(option.summary)}</span>
                    </button>
                  `,
                )
                .join("")}
            </div>
            <h2 class="panel-title" style="margin-top:18px">开局身份</h2>
            <div class="option-stack">
              ${(origin.options || [])
                .map(
                  (option) => `
                    <button class="option-button ${state.selectedOptions.player_origin === option.id ? "is-selected" : ""}" data-action="select-origin" data-value="${safeText(option.id)}">
                      <strong>${safeText(option.display_name)}</strong>
                      <span>${safeText(option.summary)}</span>
                    </button>
                  `,
                )
                .join("")}
            </div>
            <div class="screen-actions" style="margin-top:18px">
              <button class="primary-button" data-action="begin-world">点亮档案</button>
              <button class="ghost-button" data-action="use-recommended">使用推荐配置</button>
            </div>
          </aside>
        </section>
      </main>
    `;
  }

  function openingSegment() {
    const state = getState();
    const segments = ((state.data.opening || {}).segments) || [];
    return segments[state.openingIndex] || segments[0] || null;
  }

  function renderOpening() {
    const segment = openingSegment();
    if (!segment) {
      navigate("map");
      renderApp();
      return;
    }
    const lines = Array.isArray(segment.lines) ? segment.lines : [];
    const isBlack = segment.kind === "black_screen_text";
    const scene = ["distant_map", "crisis_alert", "player_awakening"].includes(
      segment.visual && segment.visual.scene,
    )
      ? segment.visual.scene
      : "distant_map";
    const sceneUrl = getOpeningSceneUrl(scene);
    root.innerHTML = `
      <main class="opening-screen">
        <section class="opening-frame opening-frame--${isBlack ? "text" : "scene"}">
          ${
            isBlack
              ? `<div class="opening-lines">${lines.map((line) => `<div>${safeText(line)}</div>`).join("")}</div>`
              : `<div class="opening-card opening-card--${scene}">
                  ${sceneUrl ? `<img class="opening-scene-image" src="${safeText(sceneUrl)}" alt="${safeText(segment.display_name || "开场远景")}" loading="eager" />` : ""}
                  <div class="opening-scene-shade"></div>
                  <div class="opening-scene-caption">
                    <span>${safeText((segment.visual && segment.visual.location_label) || segment.display_name || "前线记录")}</span>
                    <p class="opening-narration">${safeText(segment.narration || "")}</p>
                  </div>
                </div>`
          }
          <div class="opening-controls">
            <button class="ghost-button" data-action="opening-skip">跳过</button>
            <button class="primary-button" data-action="opening-next">继续</button>
          </div>
        </section>
      </main>
    `;
  }

  return { openingSegment, renderOpening, renderProfile, renderWorldConfig };
}
