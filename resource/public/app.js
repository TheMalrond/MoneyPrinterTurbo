(() => {
  "use strict";

  const API_KEY_STORAGE = "vf_api_key";
  const POLL_INTERVAL_MS = 3000;
  // Cloud Run com CPU limitada pode levar bem mais que 10min pra recodificar
  // vários clipes em série + compor legenda + render final num vídeo mais
  // longo — 10min desistia antes do servidor terminar (visto nos logs: um
  // vídeo de 14 clipes ainda estava processando aos 7min30, só entrando na
  // etapa final mais pesada).
  const POLL_TIMEOUT_MS = 20 * 60 * 1000;

  const STATE_FAILED = -1;
  const STATE_COMPLETE = 1;

  const el = (id) => document.getElementById(id);

  const settingsPanel = el("panel-settings");
  const apiKeyInput = el("input-api-key");
  const btnSettings = el("btn-settings");
  const btnSaveKey = el("btn-save-key");
  const btnCloseSettings = el("btn-close-settings");

  const form = el("form-video");
  const btnSubmit = el("btn-submit");

  const selectBgmMood = el("select-bgm-mood");
  const bgmTrackPicker = el("bgm-track-picker");

  const statusPanel = el("panel-status");
  const statusWorking = el("status-working");
  const statusText = el("status-text");
  const statusError = el("status-error");
  const errorText = el("error-text");
  const btnRetry = el("btn-retry");
  const statusDone = el("status-done");
  const videoResult = el("video-result");
  const linkDownload = el("link-download");
  const btnNew = el("btn-new");

  let pollTimer = null;
  let pollDeadline = 0;

  function getApiKey() {
    return localStorage.getItem(API_KEY_STORAGE) || "";
  }

  function setApiKey(key) {
    localStorage.setItem(API_KEY_STORAGE, key);
  }

  function openSettings() {
    apiKeyInput.value = getApiKey();
    settingsPanel.classList.remove("hidden");
  }

  function closeSettings() {
    settingsPanel.classList.add("hidden");
  }

  btnSettings.addEventListener("click", () => {
    settingsPanel.classList.contains("hidden") ? openSettings() : closeSettings();
  });

  btnCloseSettings.addEventListener("click", closeSettings);

  btnSaveKey.addEventListener("click", () => {
    setApiKey(apiKeyInput.value.trim());
    closeSettings();
  });

  function showCard(name) {
    form.classList.toggle("hidden", name !== "form");
    statusPanel.classList.toggle("hidden", name !== "status");
  }

  function showStatusWorking(message) {
    statusWorking.classList.remove("hidden");
    statusError.classList.add("hidden");
    statusDone.classList.add("hidden");
    statusText.textContent = message;
  }

  function showStatusError(message) {
    statusWorking.classList.add("hidden");
    statusError.classList.remove("hidden");
    statusDone.classList.add("hidden");
    errorText.textContent = message;
  }

  function showStatusDone(videoUrl) {
    statusWorking.classList.add("hidden");
    statusError.classList.add("hidden");
    statusDone.classList.remove("hidden");
    videoResult.src = videoUrl;
    linkDownload.href = videoUrl;
  }

  function stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  async function apiFetch(path, options = {}) {
    const headers = Object.assign({}, options.headers, {
      "x-api-key": getApiKey(),
    });
    const response = await fetch(path, Object.assign({}, options, { headers }));
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    let body = null;
    try {
      body = await response.json();
    } catch (err) {
      // resposta sem corpo JSON (ex.: 5xx genérico)
    }
    if (!response.ok) {
      const message =
        (body && (body.message || body.detail)) ||
        `Erro ${response.status} ao contactar o servidor.`;
      throw new Error(message);
    }
    return body;
  }

  // --- Trilha sonora por humor ---
  // As faixas de prévia são servidas sem exigir x-api-key (ver public_router
  // no backend) de propósito: <audio src> não consegue mandar cabeçalho
  // customizado, e buscar o áudio via fetch+Blob antes de tocar atrasa o
  // play() além da janela de gesto do usuário — o navegador bloqueia a
  // reprodução (autoplay policy). Tocar direto via src evita os dois problemas
  // e ainda aproveita o Range request nativo do navegador (começa mais rápido).

  let bgmMoodsCache = null;
  let bgmSelectedFile = "";
  const previewAudio = new Audio();
  let activePreviewButton = null;

  function friendlyTrackName(filename) {
    let name = filename.replace(/\.[^.]+$/, "");
    name = name.replace(/^mixkit-/, "").replace(/-\d+$/, "");
    name = name.replace(/-/g, " ").trim();
    return name.replace(/\b\w/g, (c) => c.toUpperCase()) || filename;
  }

  async function loadBgmMoods() {
    if (bgmMoodsCache) return bgmMoodsCache;
    const body = await apiFetch("/api/v1/musics/moods");
    bgmMoodsCache = (body && body.data && body.data.moods) || {};
    return bgmMoodsCache;
  }

  function stopPreview() {
    previewAudio.pause();
    if (activePreviewButton) {
      activePreviewButton.textContent = "▶";
      activePreviewButton = null;
    }
  }

  previewAudio.addEventListener("ended", stopPreview);
  previewAudio.addEventListener("loadedmetadata", () => {
    if (previewAudio.duration && isFinite(previewAudio.duration)) {
      previewAudio.currentTime = previewAudio.duration * 0.4;
    }
  });

  function togglePreview(file, button) {
    if (activePreviewButton === button) {
      stopPreview();
      return;
    }
    stopPreview();
    previewAudio.src = `/api/v1/musics/preview/${file}`;
    previewAudio
      .play()
      .then(() => {
        button.textContent = "⏸";
        activePreviewButton = button;
      })
      .catch(() => {
        button.textContent = "▶";
      });
  }

  async function renderBgmTrackPicker(mood) {
    stopPreview();
    if (!mood) {
      bgmTrackPicker.classList.add("hidden");
      bgmTrackPicker.innerHTML = "";
      bgmSelectedFile = "";
      return;
    }

    bgmTrackPicker.innerHTML = '<p class="hint">Carregando faixas...</p>';
    bgmTrackPicker.classList.remove("hidden");

    let moods;
    try {
      moods = await loadBgmMoods();
    } catch (err) {
      bgmTrackPicker.innerHTML = '<p class="hint">Não foi possível carregar as faixas agora.</p>';
      return;
    }

    const tracks = moods[mood] || [];
    if (!tracks.length) {
      bgmTrackPicker.innerHTML = '<p class="hint">Nenhuma faixa cadastrada nesse humor ainda.</p>';
      bgmSelectedFile = "";
      return;
    }

    bgmTrackPicker.innerHTML = "";
    bgmSelectedFile = tracks[0].file;

    tracks.forEach((track, index) => {
      const row = document.createElement("label");
      row.className = "track-row";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "bgm-track-choice";
      radio.value = track.file;
      radio.checked = index === 0;
      radio.addEventListener("change", () => {
        bgmSelectedFile = track.file;
      });

      const name = document.createElement("span");
      name.className = "track-name";
      name.textContent = friendlyTrackName(track.name);

      const previewBtn = document.createElement("button");
      previewBtn.type = "button";
      previewBtn.className = "track-preview-btn";
      previewBtn.textContent = "▶";
      previewBtn.addEventListener("click", () => togglePreview(track.file, previewBtn));

      row.appendChild(radio);
      row.appendChild(name);
      row.appendChild(previewBtn);
      bgmTrackPicker.appendChild(row);
    });
  }

  selectBgmMood.addEventListener("change", () => {
    renderBgmTrackPicker(selectBgmMood.value);
  });

  function selectedVideoSources() {
    const sources = [];
    if (el("check-source-ybera").checked) sources.push("ybera_bank");
    if (el("check-source-pexels").checked) sources.push("pexels");
    return sources;
  }

  function buildRequestBody() {
    const script = el("input-script").value.trim();
    const terms = el("input-terms").value.trim();
    const subject = script.slice(0, 60) || "Vídeo gerado via Video Factory";

    return {
      video_subject: subject,
      video_script: script,
      video_terms: terms,
      video_source: selectedVideoSources().join(","),
      video_aspect: el("select-aspect").value,
      video_concat_mode: "random",
      video_clip_duration: 5,
      video_count: 1,
      voice_name: el("select-voice").value,
      voice_rate: 1.0,
      bgm_type: bgmSelectedFile ? "custom" : "none",
      bgm_file: bgmSelectedFile,
      bgm_volume: 0.15,
      subtitle_enabled: true,
      subtitle_position: el("select-subtitle-position").value,
      font_name: "BeVietnamPro-Bold.ttf",
      font_size: 66,
      text_fore_color: el("input-subtitle-color").value,
      stroke_color: "#000000",
      stroke_width: 1.5,
    };
  }

  async function pollTask(taskId) {
    if (Date.now() > pollDeadline) {
      showStatusError(
        "A geração está demorando muito mais do que o normal. Vídeos mais longos podem levar vários minutos no servidor — se isso persistir, tente um roteiro mais curto ou verifique o painel do servidor."
      );
      return;
    }
    try {
      const body = await apiFetch(`/api/v1/tasks/${taskId}`);
      const data = (body && body.data) || {};

      if (data.state === STATE_COMPLETE) {
        const videos = data.videos || data.combined_videos || [];
        if (videos.length > 0) {
          showStatusDone(videos[0]);
        } else {
          showStatusError("Vídeo concluído, mas nenhum arquivo foi retornado.");
        }
        return;
      }

      if (data.state === STATE_FAILED) {
        showStatusError(
          data.message || data.error || "Falha ao gerar o vídeo. Tente ajustar o roteiro ou os termos visuais."
        );
        return;
      }

      const progress = typeof data.progress === "number" ? data.progress : 0;
      showStatusWorking(`Gerando vídeo... ${progress}%`);
      pollTimer = setTimeout(() => pollTask(taskId), POLL_INTERVAL_MS);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        showStatusError("Chave de acesso inválida ou ausente. Abra as configurações (⚙) e verifique.");
        return;
      }
      showStatusError(err.message || "Erro ao consultar o status do vídeo.");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!getApiKey()) {
      openSettings();
      return;
    }

    if (selectedVideoSources().length === 0) {
      showCard("status");
      showStatusError("Selecione pelo menos uma fonte de imagens.");
      return;
    }

    btnSubmit.disabled = true;
    showCard("status");
    showStatusWorking("Enviando pedido...");

    try {
      const body = await apiFetch("/api/v1/videos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequestBody()),
      });
      const taskId = body && body.data && body.data.task_id;
      if (!taskId) {
        throw new Error("Resposta do servidor não trouxe um task_id.");
      }
      pollDeadline = Date.now() + POLL_TIMEOUT_MS;
      showStatusWorking("Gerando vídeo... 0%");
      pollTask(taskId);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        showStatusError("Chave de acesso inválida ou ausente. Abra as configurações (⚙) e verifique.");
      } else {
        showStatusError(err.message || "Não foi possível iniciar a geração do vídeo.");
      }
    } finally {
      btnSubmit.disabled = false;
    }
  });

  btnRetry.addEventListener("click", () => {
    stopPolling();
    showCard("form");
  });

  btnNew.addEventListener("click", () => {
    stopPolling();
    showCard("form");
  });

  if (!getApiKey()) {
    // Primeiro acesso: pede a chave antes de qualquer tentativa de gerar vídeo.
    openSettings();
  }

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // instalação do PWA é best-effort; a geração de vídeo funciona sem ele.
      });
    });
  }
})();
