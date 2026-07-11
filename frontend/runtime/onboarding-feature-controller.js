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
            <h1 class="screen-title">Compiler</h1>
            <p class="screen-subtitle">
              每份档案都会建立独立世界、前线与可研发装置。选择一个已经准备好的世界实例开始体验。
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
          <div class="profile-visual" aria-label="世界实例预览">
            ${previewUrl ? `<img src="${safeText(previewUrl)}" alt="当前世界实例预览" loading="eager" />` : ""}
            <div class="profile-visual-caption">
              <span>世界实例</span>
              <strong>构想会在本局中成为可玩的防线</strong>
              <small>世界、任务与研发结果沿同一套玩法规则持续生长。</small>
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
    const catalog = state.data.worldCatalog || { worlds: [] };
    const worlds = Array.isArray(catalog.worlds) ? catalog.worlds : [];
    const selectedWorld =
      worlds.find((item) => item.world_id === state.selectedWorldId) || worlds[0] || {};
    root.innerHTML = `
      <main class="screen">
        ${screenHeader("建立本局档案", "选择世界实例、创造性与开局身份。", "开局建档")}
        <section class="world-choice-strip" aria-label="世界实例">
          ${worlds
            .map(
              (item) => `
                <button class="world-choice ${state.selectedWorldId === item.world_id ? "is-selected" : ""}" data-action="select-world" data-value="${safeText(item.world_id)}" ${item.status === "ready" ? "" : "disabled"}>
                  <span class="world-choice-status">${item.status === "ready" ? "可进入" : "形成中"}</span>
                  <strong>${safeText(item.display_name)}</strong>
                  <small>${safeText(item.tagline || "本局世界正在建立。")}</small>
                  <span class="world-choice-style">${safeText(item.visual_style_name || "伪三维")}</span>
                </button>
              `,
            )
            .join("")}
        </section>
        <section class="config-grid">
          <aside class="panel">
            <h2 class="panel-title">世界书</h2>
            <p class="panel-text">${safeText(config.worldbook_display_name || "长夜灯火")}</p>
            <div class="tag-row">
              ${(selectedWorld.theme_tags || []).slice(0, 4).map((tag) => `<span class="tag">${safeText(tag)}</span>`).join("")}
            </div>
            <p class="panel-text">${safeText(selectedWorld.tagline || "第一处危机已经出现。")}</p>
          </aside>
          <div class="world-preview" aria-label="画风预览">
            ${previewUrl ? `<img src="${safeText(previewUrl)}" alt="当前世界画风预览" loading="eager" />` : ""}
            <div class="world-preview-caption">
              <div class="eyebrow">画风</div>
              <h2 class="panel-title">${safeText(config.visual_style_display_name || "灯塬旧朝·伪三维")}</h2>
              <p class="panel-text">道路、部署点与目标由本局玩法包约束，画面随世界风格呈现。</p>
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
