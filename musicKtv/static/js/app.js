/* ── 音乐KTV 前端逻辑 ───────────────────────────── */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── 全局状态 ────────────────────────────────────
let playlist = [];
let sungList = [];
let currentSong = null;
let audioCtx = null;
let audioEl = null;
let mediaRecorder = null;
let recordedChunks = [];
let recStartTime = 0;
let recTimerId = null;
let analyserNode = null;
let waveformAnimId = null;
let monitorNodes = [];
let monitorStream = null;
let cachedSearchResults = [];
let currentLyrics = [];
let lyricEls = [];
let lyricSyncId = null;
let progressRafId = null;
let kgeMode = null;          // 'record' | 'playback'
let isExiting = false;

// ── DOM 初始化 ──────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  loadPlaylist();
  loadSungList();
  loadRecordings();
  $("#search-btn").addEventListener("click", doSearch);
  $("#search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });
  $("#btn-start-kge").addEventListener("click", startKge);
  $("#clear-playlist-btn").addEventListener("click", clearPlaylist);
  $("#clear-sung-btn").addEventListener("click", clearSungList);
  $("#kge-back-btn").addEventListener("click", exitKgeMode);
  $("#kge-stop-btn").addEventListener("click", stopRecording);
  $("#clear-recordings-btn").addEventListener("click", clearAllRecordings);
  initProgressSeek();
});

// ── Tab 切换 ────────────────────────────────────

function initTabs() {
  $$(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      $$(".tab-panel").forEach((p) => p.classList.remove("active"));
      $(`#tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "recordings") {
        loadRecordings();
        stopAnyPlayback();
      }
    });
  });
}

function stopAnyPlayback() {
  if (audioEl && !audioEl.paused) {
    audioEl.pause();
    audioEl = null;
  }
}

// ── Toast ───────────────────────────────────────

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(el._timeout);
  el._timeout = setTimeout(() => el.classList.remove("show"), 2500);
}

// ── API ────────────────────────────────────────

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  return res.json();
}

// ── 搜索 ────────────────────────────────────────

async function doSearch() {
  const q = $("#search-input").value.trim();
  if (!q) return toast("请输入关键词", true);

  const btn = $("#search-btn");
  btn.disabled = true;
  btn.textContent = "搜索中...";

  try {
    const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
    if (data.error) { toast(data.error, true); return; }
    cachedSearchResults = data.results || [];
    renderSearchResults(cachedSearchResults);
  } catch (e) {
    toast("搜索失败: " + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "搜索";
  }
}

function renderSearchResults(results) {
  const container = $("#search-results");
  cachedSearchResults = results;

  if (!results || !results.length) {
    container.innerHTML = '<p class="placeholder">没有找到相关结果</p>';
    return;
  }

  container.innerHTML = results.map((r) => {
    const inPlaylist = playlist.some((s) => s.url === r.url);
    const cachedTag = r.cached ? ' <span class="cached-badge">已缓存</span>' : '';
    return `
      <div class="song-card">
        <img class="thumb" src="${esc(r.thumbnail)}" alt="" onerror="this.style.display='none'">
        <div class="info">
          <div class="name" title="${esc(r.title)}">${esc(r.title)}${cachedTag}</div>
          <div class="meta">${esc(r.artist)} ${r.duration ? "· " + r.duration : ""}</div>
        </div>
        <div class="btn-row">
          <button class="btn-kge-sm" data-json='${esc(JSON.stringify(r))}'>K歌</button>
          <button class="btn-add" data-json='${esc(JSON.stringify(r))}' ${inPlaylist ? "disabled" : ""}>
            ${inPlaylist ? "已点" : "点歌"}
          </button>
        </div>
      </div>`;
  }).join("");

  container.querySelectorAll(".btn-add").forEach((btn) => {
    btn.addEventListener("click", () => {
      const song = JSON.parse(btn.dataset.json);
      addToPlaylist(song);
      btn.disabled = true;
      btn.textContent = "已点";
    });
  });

  container.querySelectorAll(".btn-kge-sm").forEach((btn) => {
    btn.addEventListener("click", () => {
      const song = JSON.parse(btn.dataset.json);
      startKgeFromSearch(song);
    });
  });
}

function refreshSearchButtons() {
  if (!cachedSearchResults.length) return;
  renderSearchResults(cachedSearchResults);
}

// ── 已点歌单 ────────────────────────────────────

async function loadPlaylist() {
  try {
    const data = await api("/api/playlist");
    playlist = data.playlist || [];
    renderPlaylist();
  } catch (e) { /* ignore */ }
}

async function addToPlaylist(song) {
  try {
    const data = await api("/api/playlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(song),
    });
    playlist = data.playlist || [];
    renderPlaylist();
    toast("已添加到歌单");
  } catch (e) {
    toast("添加失败", true);
  }
}

async function removeFromPlaylist(id) {
  try {
    const data = await api(`/api/playlist?id=${encodeURIComponent(id)}`, { method: "DELETE" });
    playlist = data.playlist || [];
    if (currentSong && currentSong.id === id) {
      currentSong = null;
      resetStage();
    }
    renderPlaylist();
    refreshSearchButtons();
  } catch (e) {
    toast("删除失败", true);
  }
}

async function clearPlaylist() {
  for (const s of [...playlist]) {
    await api(`/api/playlist?id=${encodeURIComponent(s.id)}`, { method: "DELETE" });
  }
  playlist = [];
  currentSong = null;
  resetStage();
  renderPlaylist();
  refreshSearchButtons();
  toast("歌单已清空");
}

function renderPlaylist() {
  const container = $("#playlist");
  const count = $("#playlist-count");
  const actions = $("#playlist-actions");

  count.textContent = playlist.length;
  actions.style.display = playlist.length > 0 ? "block" : "none";

  if (!playlist.length) {
    container.innerHTML = '<p class="placeholder">还没有点歌，去搜索添加吧</p>';
    return;
  }

  container.innerHTML = playlist.map((s, i) => `
    <div class="playlist-item${currentSong && currentSong.id === s.id ? " current" : ""}">
      <span class="idx">${i + 1}</span>
      <div class="info">
        <div class="name" title="${esc(s.title)}">${esc(s.title)}</div>
        <div class="src">${esc(s.artist || "")}</div>
      </div>
      <button class="btn-del" data-id="${esc(s.id)}" title="移除">&times;</button>
    </div>
  `).join("");

  container.querySelectorAll(".playlist-item").forEach((el, i) => {
    el.addEventListener("click", (e) => {
      if (e.target.classList.contains("btn-del")) return;
      selectSong(playlist[i]);
    });
  });

  container.querySelectorAll(".btn-del").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      removeFromPlaylist(btn.dataset.id);
    });
  });
}

// ── 已唱列表 ────────────────────────────────────

async function loadSungList() {
  try {
    const data = await api("/api/sung");
    sungList = data.sung || [];
    renderSungList();
  } catch (e) { /* ignore */ }
}

async function addToSungList(song) {
  try {
    const data = await api("/api/sung", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(song),
    });
    sungList = data.sung || [];
    renderSungList();
  } catch (e) { /* ignore */ }
}

async function clearSungList() {
  await api("/api/sung", { method: "DELETE" });
  sungList = [];
  renderSungList();
  toast("已唱列表已清空");
}

function renderSungList() {
  const container = $("#sung-list");
  const count = $("#sung-count");
  const actions = $("#sung-actions");

  count.textContent = sungList.length;
  actions.style.display = sungList.length > 0 ? "block" : "none";

  if (!sungList.length) {
    container.innerHTML = '<p class="placeholder">还没有唱过歌</p>';
    return;
  }

  container.innerHTML = sungList.map((s, i) => `
    <div class="playlist-item">
      <span class="idx">${i + 1}</span>
      <div class="info">
        <div class="name" title="${esc(s.title)}">${esc(s.title)}</div>
        <div class="src">${esc(s.artist || "")}</div>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".playlist-item").forEach((el, i) => {
    el.addEventListener("click", () => {
      selectSong(sungList[i]);
    });
  });
}

// ── 选中歌曲 ────────────────────────────────────

function selectSong(song) {
  currentSong = song;
  $("#now-playing").textContent = song.title;
  $("#now-artist").textContent = song.artist || "";
  $("#btn-start-kge").disabled = false;
  renderPlaylist();
}

function resetStage() {
  $("#now-playing").textContent = "选择歌曲开始K歌";
  $("#now-artist").textContent = "";
  $("#btn-start-kge").disabled = true;
}

// ══════════════════════════════════════════════════
// K歌全屏模式
// ══════════════════════════════════════════════════

async function startKgeFromSearch(song) {
  currentSong = song;
  addToSungList(song);
  await enterKgeMode("record");
}

async function startKge() {
  if (!currentSong) return toast("请先从歌单选择歌曲", true);
  addToSungList(currentSong);
  await enterKgeMode("record");
}

function showKgeOverlay() {
  $("#kge-overlay").style.display = "";
  $("#kge-stop-btn").style.display = "none";
  $("#kge-rec-dot").style.display = "none";
  $("#kge-rec-timer").style.display = "none";
  $("#kge-waveform").style.display = "none";
  $("#kge-status-text").textContent = "";
  $("#kge-time-current").textContent = "00:00";
  $("#kge-time-total").textContent = "00:00";
  $("#kge-progress-fill").style.width = "0%";
  $("#lyrics-inner").innerHTML = "";
}

async function pollDownloadProgress(taskId) {
  return new Promise((resolve) => {
    const poll = async () => {
      try {
        const data = await api(`/api/download/status/${taskId}`);
        if (data.status === "complete") {
          $("#kge-progress-fill").style.width = "100%";
          $("#kge-status-text").textContent = "下载完成";
          resolve({ filename: data.filename });
        } else if (data.status === "error") {
          resolve(null);
        } else {
          const pct = data.progress || 0;
          $("#kge-progress-fill").style.width = pct + "%";
          $("#kge-time-current").textContent = pct + "%";
          if (data.speed) {
            $("#kge-time-total").textContent = data.speed;
          }
          let status = `下载中 ${pct}%`;
          if (data.eta) status += ` · 剩余 ${data.eta}`;
          $("#kge-status-text").textContent = status;
          setTimeout(poll, 500);
        }
      } catch (e) {
        resolve(null);
      }
    };
    poll();
  });
}

async function enterKgeMode(mode) {
  isExiting = false;
  kgeMode = mode;

  // 先请求麦克风权限 (在 await 之前保持 user gesture)
  if (mode === "record") {
    try {
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStream.getTracks().forEach((t) => t.stop());
    } catch (e) {
      toast("麦克风不可用: " + e.message, true);
      kgeMode = null;
      return;
    }
  }

  const btn = $("#btn-start-kge");
  btn.disabled = true;
  btn.textContent = "下载中...";

  try {
    // 下载伴奏
    const dlResp = await api("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentSong.url, title: currentSong.title }),
    });
    if (dlResp.error) { toast(dlResp.error, true); btn.disabled = false; btn.textContent = "开始K歌"; return; }

    let audioUrl;

    if (dlResp.cached) {
      currentSong._dlFilename = dlResp.filename;
      audioUrl = `/downloads/${encodeURIComponent(dlResp.filename)}`;
      toast("已缓存，直接播放");
    } else if (dlResp.task_id) {
      // 异步下载 — 进入全屏显示进度
      showKgeOverlay();
      btn.style.display = "none";
      $("#kge-song-title").textContent = currentSong.title;
      $("#kge-song-artist").textContent = currentSong.artist || "";
      $("#lyrics-inner").innerHTML = '<div class="lyric-line" style="color:#888">准备下载伴奏...</div>';
      $("#kge-status-text").textContent = "下载中";

      const result = await pollDownloadProgress(dlResp.task_id);
      if (!result) {
        toast("下载失败", true);
        exitKgeMode();
        return;
      }
      currentSong._dlFilename = result.filename;
      audioUrl = `/downloads/${encodeURIComponent(result.filename)}`;

      // 清除下载进度显示
      $("#kge-progress-fill").style.width = "0%";
      $("#kge-time-current").textContent = "00:00";
      $("#kge-time-total").textContent = "00:00";
      $("#kge-status-text").textContent = "";
    } else {
      throw new Error("未知的下载响应");
    }

    // 加载歌词
    currentLyrics = [];
    lyricEls = [];
    try {
      const lrcData = await api(`/api/lyrics?title=${encodeURIComponent(currentSong.title)}&artist=${encodeURIComponent(currentSong.artist || "")}`);
      if (lrcData.lyrics) {
        currentLyrics = parseLyrics(lrcData.lyrics);
      }
    } catch (e) { /* ignore */ }

    // 确保进入全屏 (cached 路径可能还未进入)
    if (dlResp.cached) {
      showKgeOverlay();
      btn.style.display = "none";
      $("#kge-song-title").textContent = currentSong.title;
      $("#kge-song-artist").textContent = currentSong.artist || "";
    }

    // 渲染歌词
    renderLyrics();

    // 创建音频元素
    audioEl = new Audio(audioUrl);
    audioEl.addEventListener("ended", onAudioEnded);
    audioEl.addEventListener("error", () => {
      toast("音频加载失败", true);
      exitKgeMode();
    });

    // 等待音频可播放
    await new Promise((resolve, reject) => {
      audioEl.addEventListener("canplaythrough", resolve, { once: true });
      audioEl.addEventListener("error", () => reject(new Error("音频加载失败")), { once: true });
      audioEl.load();
      setTimeout(resolve, 10000);
    });

    // 倒计时
    if (mode === "record") {
      await countdown(3);
    }

    // 开始
    if (mode === "record") {
      await startRecordingAndPlayback();
    } else {
      startPlaybackOnly();
    }
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false;
    btn.textContent = "开始K歌";
    btn.style.display = "";
    exitKgeMode();
  }
}

// ── 退出 K歌模式 ────────────────────────────────

function exitKgeMode() {
  isExiting = true;

  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  if (mediaRecorder && mediaRecorder.stream) {
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
  }
  if (audioEl) {
    audioEl.pause();
    audioEl = null;
  }
  stopMonitor();
  stopWaveform();
  if (lyricSyncId) cancelAnimationFrame(lyricSyncId);
  if (progressRafId) cancelAnimationFrame(progressRafId);
  if (recTimerId) clearInterval(recTimerId);
  if (audioCtx && audioCtx.state !== "closed") {
    audioCtx.close();
    audioCtx = null;
  }
  analyserNode = null;
  monitorNodes = [];
  monitorStream = null;
  mediaRecorder = null;
  recordedChunks = [];
  currentLyrics = [];
  lyricEls = [];
  kgeMode = null;

  $("#kge-overlay").style.display = "none";
  $("#btn-start-kge").disabled = !!currentSong;
  $("#btn-start-kge").textContent = "开始K歌";
  $("#btn-start-kge").style.display = currentSong ? "" : "none";
  if (!currentSong) {
    $("#btn-start-kge").disabled = true;
    $("#btn-start-kge").style.display = "";
  }
}

// ── 倒计时 ──────────────────────────────────────

function countdown(seconds) {
  return new Promise((resolve) => {
    const cd = $("#kge-countdown");
    cd.style.display = "";
    let n = seconds;

    const tick = () => {
      if (n <= 0) {
        cd.textContent = "";
        cd.style.display = "none";
        resolve();
        return;
      }
      cd.textContent = n;
      cd.style.animation = "none";
      void cd.offsetWidth;
      cd.style.animation = "";
      n--;
      setTimeout(tick, 800);
    };
    tick();
  });
}

// ── 录制 + 播放 ─────────────────────────────────

async function startRecordingAndPlayback() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

  audioCtx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
  const source = audioCtx.createMediaStreamSource(stream);
  analyserNode = audioCtx.createAnalyser();
  analyserNode.fftSize = 256;
  source.connect(analyserNode);

  startMonitor(stream);

  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) recordedChunks.push(e.data);
  };
  mediaRecorder.onstop = handleRecordingStop;

  mediaRecorder.start();
  recStartTime = Date.now();
  audioEl.play();

  // UI
  $("#kge-stop-btn").style.display = "";
  $("#kge-rec-dot").style.display = "";
  $("#kge-rec-timer").style.display = "";
  $("#kge-status-text").textContent = "录制中";
  $("#kge-waveform").style.display = "";

  updateRecTimer();
  recTimerId = setInterval(updateRecTimer, 200);
  startProgressLoop();
  startWaveform();
  startLyricSync();
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  if (audioEl) {
    audioEl.pause();
  }
  if (mediaRecorder && mediaRecorder.stream) {
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
  }
  if (recTimerId) clearInterval(recTimerId);
  stopWaveform();
  stopMonitor();
  if (progressRafId) cancelAnimationFrame(progressRafId);
  if (lyricSyncId) cancelAnimationFrame(lyricSyncId);

  $("#kge-stop-btn").style.display = "none";
  $("#kge-rec-dot").style.display = "none";
  $("#kge-rec-timer").style.display = "none";
  $("#kge-waveform").style.display = "none";
}

function onAudioEnded() {
  if (kgeMode === "record" && mediaRecorder && mediaRecorder.state === "recording") {
    stopRecording();
  }
  if (kgeMode === "playback") {
    $("#kge-status-text").textContent = "播放完毕";
  }
}

async function handleRecordingStop() {
  if (isExiting || !recordedChunks.length) return;

  $("#kge-status-text").textContent = "合成中...";

  const voiceBlob = new Blob(recordedChunks, { type: "audio/webm" });
  const formData = new FormData();
  formData.append("voice", voiceBlob, "voice.webm");
  formData.append("accompaniment", currentSong._dlFilename || "");
  formData.append("title", currentSong.title || "recording");

  try {
    const res = await fetch("/api/mix", { method: "POST", body: formData });
    const data = await res.json();
    if (data.error) { $("#kge-status-text").textContent = "合成失败"; return; }
    $("#kge-status-text").textContent = "录制完成!";
    recordedChunks = [];
    setTimeout(() => {
      exitKgeMode();
      $('[data-tab="recordings"]').click();
    }, 1200);
  } catch (e) {
    $("#kge-status-text").textContent = "合成失败";
  }
}

// ── 仅播放模式 (录音列表播放) ───────────────────

function startPlaybackOnly() {
  audioEl.play();
  $("#kge-status-text").textContent = "播放中";
  startProgressLoop();
  if (currentLyrics.length) {
    startLyricSync();
  }
}

// ── 耳返 (低延迟: 干声直通 + 混响并联) ──────────

function startMonitor(stream) {
  if (!audioCtx || audioCtx.state === "closed") return;
  if (monitorNodes.length) return;

  const source = audioCtx.createMediaStreamSource(stream);
  monitorNodes = [];

  // 干声路径 (最小延迟: 只有 2 个节点)
  const highPass = audioCtx.createBiquadFilter();
  highPass.type = "highpass";
  highPass.frequency.value = 80;
  monitorNodes.push(highPass);

  const presence = audioCtx.createBiquadFilter();
  presence.type = "highshelf";
  presence.frequency.value = 2800;
  presence.gain.value = 3.5;
  monitorNodes.push(presence);

  const dryGain = audioCtx.createGain();
  dryGain.gain.value = 0.9;
  monitorNodes.push(dryGain);

  // 混响并联路径 (不影响干声延迟)
  const reverbSend = audioCtx.createGain();
  reverbSend.gain.value = 0.4;
  monitorNodes.push(reverbSend);

  const reverbReturn = audioCtx.createGain();
  reverbReturn.gain.value = 0.4;
  monitorNodes.push(reverbReturn);

  [0.033, 0.041, 0.049].forEach((dt) => {
    const delay = audioCtx.createDelay(0.5);
    delay.delayTime.value = dt;
    monitorNodes.push(delay);

    const feedback = audioCtx.createGain();
    feedback.gain.value = 0.35;
    monitorNodes.push(feedback);

    const lp = audioCtx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 5000;
    monitorNodes.push(lp);

    reverbSend.connect(delay);
    delay.connect(feedback);
    feedback.connect(lp);
    lp.connect(delay);
    delay.connect(reverbReturn);
  });

  // 总输出
  const masterGain = audioCtx.createGain();
  masterGain.gain.value = 0.95;
  monitorNodes.push(masterGain);

  // 路由: source → HP → presence → split → dry + reverb → master → out
  source.connect(highPass);
  highPass.connect(presence);
  presence.connect(dryGain);
  presence.connect(reverbSend);
  dryGain.connect(masterGain);
  reverbReturn.connect(masterGain);
  masterGain.connect(audioCtx.destination);

  monitorStream = stream;
}

function stopMonitor() {
  monitorNodes.forEach((n) => {
    try { n.disconnect(); } catch (e) { /* ignore */ }
  });
  monitorNodes = [];
  monitorStream = null;
}

// ── 歌词 ────────────────────────────────────────

function parseLyrics(lrc) {
  const lines = [];
  const regex = /\[(\d{1,3}):(\d{2})(?:\.(\d{2,3}))?\]\s*(.*)/g;
  let match;

  while ((match = regex.exec(lrc)) !== null) {
    const min = parseInt(match[1], 10);
    const sec = parseInt(match[2], 10);
    let ms = match[3] ? parseInt(match[3].padEnd(3, "0"), 10) : 0;
    const time = min * 60 + sec + ms / 1000;
    const text = match[4].trim();
    if (text) {
      lines.push({ time, text });
    }
  }

  lines.sort((a, b) => a.time - b.time);
  return lines;
}

function renderLyrics() {
  const container = $("#lyrics-inner");
  container.innerHTML = "";

  if (!currentLyrics.length) {
    container.innerHTML = '<div class="lyric-line" style="color:#888">暂无歌词</div>';
    return;
  }

  lyricEls = currentLyrics.map((l, i) => {
    const el = document.createElement("div");
    el.className = "lyric-line future";
    el.textContent = l.text;
    el.dataset.index = i;
    container.appendChild(el);
    return el;
  });
}

function startLyricSync() {
  let lastIdx = -1;

  const tick = () => {
    if (!audioEl || !lyricEls.length) {
      lyricSyncId = requestAnimationFrame(tick);
      return;
    }

    const t = audioEl.currentTime;
    let currentIdx = -1;
    for (let i = currentLyrics.length - 1; i >= 0; i--) {
      if (t >= currentLyrics[i].time) {
        currentIdx = i;
        break;
      }
    }

    if (currentIdx !== lastIdx) {
      lyricEls.forEach((el, i) => {
        el.classList.remove("future", "current", "past");
        if (i < currentIdx) el.classList.add("past");
        else if (i === currentIdx) {
          el.classList.add("current");
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        } else {
          el.classList.add("future");
        }
      });
      lastIdx = currentIdx;
    }

    lyricSyncId = requestAnimationFrame(tick);
  };
  lyricSyncId = requestAnimationFrame(tick);
}

// ── 进度条 ──────────────────────────────────────

function startProgressLoop() {
  const tick = () => {
    if (!audioEl || audioEl.paused) {
      progressRafId = requestAnimationFrame(tick);
      return;
    }
    const dur = audioEl.duration;
    const cur = audioEl.currentTime;
    if (dur && isFinite(dur)) {
      const pct = (cur / dur) * 100;
      $("#kge-progress-fill").style.width = pct + "%";
      $("#kge-time-current").textContent = fmtTime(cur);
      $("#kge-time-total").textContent = fmtTime(dur);
    }
    progressRafId = requestAnimationFrame(tick);
  };
  progressRafId = requestAnimationFrame(tick);
}

// ── 进度条拖动 ──────────────────────────────────

function initProgressSeek() {
  const track = $("#kge-progress-track");
  let dragging = false;

  const seek = (e) => {
    if (!audioEl || !audioEl.duration || !isFinite(audioEl.duration)) return;
    const rect = track.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    audioEl.currentTime = pct * audioEl.duration;
  };

  track.addEventListener("mousedown", (e) => {
    dragging = true;
    seek(e);
    e.preventDefault();
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    seek(e);
  });

  document.addEventListener("mouseup", () => {
    dragging = false;
  });

  // 触摸事件
  track.addEventListener("touchstart", (e) => {
    dragging = true;
    seek(e.touches[0]);
    e.preventDefault();
  });

  document.addEventListener("touchmove", (e) => {
    if (!dragging) return;
    seek(e.touches[0]);
  });

  document.addEventListener("touchend", () => {
    dragging = false;
  });
}

// ── 录制计时器 ──────────────────────────────────

function updateRecTimer() {
  const elapsed = Math.floor((Date.now() - recStartTime) / 1000);
  $("#kge-rec-timer").textContent = fmtTime(elapsed);
}

// ── 波形 ────────────────────────────────────────

function startWaveform() {
  const canvas = $("#kge-waveform");
  const ctx = canvas.getContext("2d");
  canvas.style.display = "";

  const draw = () => {
    if (!analyserNode) return;
    const data = new Uint8Array(analyserNode.frequencyBinCount);
    analyserNode.getByteFrequencyData(data);

    const w = canvas.width = canvas.offsetWidth;
    const h = canvas.height = canvas.offsetHeight;
    ctx.clearRect(0, 0, w, h);

    const barW = (w / data.length) * 2;
    let x = 0;
    ctx.fillStyle = "#6c5ce7";
    for (let i = 0; i < data.length; i++) {
      const v = data[i] / 255;
      const barH = v * h * 0.8;
      ctx.fillRect(x, h - barH, barW - 1, barH);
      x += barW;
    }
    waveformAnimId = requestAnimationFrame(draw);
  };
  draw();
}

function stopWaveform() {
  if (waveformAnimId) cancelAnimationFrame(waveformAnimId);
  waveformAnimId = null;
  const canvas = $("#kge-waveform");
  const ctx = canvas.getContext("2d");
  if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  canvas.style.display = "none";
}

// ── 录音列表 ────────────────────────────────────

async function loadRecordings() {
  try {
    const data = await api("/api/recordings");
    renderRecordings(data.recordings || []);
  } catch (e) { /* ignore */ }
}

function renderRecordings(recordings) {
  const container = $("#recordings-list");
  const actions = $("#recordings-actions");
  const count = $("#recordings-count");

  count.textContent = recordings.length;
  actions.style.display = recordings.length > 0 ? "block" : "none";

  if (!recordings.length) {
    container.innerHTML = '<p class="placeholder">还没有录音，去K歌吧</p>';
    return;
  }
  container.innerHTML = recordings.map((r) => `
    <div class="recording-item">
      <div class="info">
        <div class="name">${esc(r.filename)}</div>
        <div class="meta">${r.size} · ${r.time}</div>
      </div>
      <button class="btn-play" data-url="/recordings/${encodeURIComponent(r.filename)}" data-filename="${esc(r.filename)}">播放</button>
      <a class="btn-dl" href="/recordings/${encodeURIComponent(r.filename)}" download>下载</a>
      <button class="btn-rec-del" data-filename="${esc(r.filename)}" title="删除">&times;</button>
    </div>
  `).join("");

  container.querySelectorAll(".btn-play").forEach((btn) => {
    btn.addEventListener("click", () => {
      playRecording(btn.dataset.url, btn.dataset.filename);
    });
  });

  container.querySelectorAll(".btn-rec-del").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const filename = btn.dataset.filename;
      try {
        await api(`/api/recordings/${encodeURIComponent(filename)}`, { method: "DELETE" });
        toast("已删除");
        loadRecordings();
      } catch (e) {
        toast("删除失败", true);
      }
    });
  });
}

async function clearAllRecordings() {
  if (!confirm("确定要删除全部录音吗?")) return;
  try {
    await api("/api/recordings", { method: "DELETE" });
    toast("已清空全部录音");
    loadRecordings();
  } catch (e) {
    toast("清空失败", true);
  }
}

async function playRecording(url, filename) {
  stopAnyPlayback();
  if (kgeMode) exitKgeMode();

  kgeMode = "playback";
  isExiting = false;

  // 尝试从文件名提取歌名以获取歌词
  const titleMatch = filename.match(/^(.+)_\d{8}_\d{6}/);
  const guessedTitle = titleMatch ? titleMatch[1] : filename;

  currentLyrics = [];
  lyricEls = [];
  try {
    const lrcData = await api(`/api/lyrics?title=${encodeURIComponent(guessedTitle)}`);
    if (lrcData.lyrics) {
      currentLyrics = parseLyrics(lrcData.lyrics);
    }
  } catch (e) { /* ignore */ }

  showKgeOverlay();
  $("#kge-song-title").textContent = guessedTitle;
  $("#kge-song-artist").textContent = "";
  renderLyrics();

  audioEl = new Audio(url);
  audioEl.addEventListener("ended", onAudioEnded);
  audioEl.addEventListener("error", () => {
    toast("音频加载失败", true);
    exitKgeMode();
  });

  await new Promise((resolve, reject) => {
    audioEl.addEventListener("canplaythrough", resolve, { once: true });
    audioEl.addEventListener("error", () => reject(new Error("加载失败")), { once: true });
    audioEl.load();
    setTimeout(resolve, 8000);
  });

  startPlaybackOnly();
}

// ── 工具函数 ────────────────────────────────────

function esc(s) {
  if (!s) return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function fmtTime(seconds) {
  if (!seconds || !isFinite(seconds)) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
