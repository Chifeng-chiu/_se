// DeepShield 模式 B：即時防護盾 content script (MV3).
// Shadow DOM 懸浮盾牌 + Mini Dashboard + <video> 擷取 + WS 即時連動 + Demo 串流。
// 設計原則：任何單點失敗（無影片 / CORS 靜音 / 後端未開）都只降級顯示，絕不拋錯影響頁面。
(function () {
  "use strict";
  if (window.__deepshield_loaded) return;
  window.__deepshield_loaded = true;

  var API_BASE = "http://localhost:8000";
  var WS_URL = "ws://localhost:8000/api/v1/ws/realtime-scan";
  var DASHBOARD = "http://localhost:5173";
  var TICK_MS = 2000;
  var MAX_SCORES = 15;

  var DEMO_LINES = [
    "現在加入老師的群組，保證獲利，飆股內線免費送",
    "名額只剩最後三十位，趕快匯款到監管帳戶卡位",
    "這件事不能告訴別人，立刻轉帳，驗證碼先給我",
  ];

  var S = {
    monitoring: false,
    demoMode: false,
    ws: null,
    wsWanted: false,
    timer: null,
    t0: 0,
    scores: [],
    lastStatus: "SAFE",
    lastTrust: 100,
    alerts: [],
    transcript: "",
    history: [], // {t, trust, status, alerts[], snippet}
    demoTick: 0,
    audioNote: "",
    videoNote: "",
    taps: new WeakMap(), // videoEl -> {ctx, analyser}
    audioRing: [], // 連續收集的時域樣本 (float, 原始取樣率)
    audioSR: 48000,
    sessionBusy: false,
  };

  // ---------- 小工具 ----------
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function bytesToB64(bytes) {
    var s = "";
    var CH = 8192;
    for (var i = 0; i < bytes.length; i += CH) {
      s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    }
    return btoa(s);
  }
  function floatTo16PCM(floats) {
    var out = new Int16Array(floats.length);
    for (var i = 0; i < floats.length; i++) {
      var v = Math.max(-1, Math.min(1, floats[i]));
      out[i] = v < 0 ? v * 32768 : v * 32767;
    }
    return new Uint8Array(out.buffer);
  }
  // 任意取樣率 float → 16kHz mono int16 base64（後端 raw-s16 退路可直接解）
  function resampleTo16k(floats, fromSR) {
    if (!floats || floats.length === 0) return "";
    var toSR = 16000;
    var ratio = fromSR / toSR;
    var n = Math.max(1, Math.floor(floats.length / ratio));
    var out = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var pos = i * ratio;
      var i0 = Math.floor(pos);
      var f = pos - i0;
      var a = floats[Math.min(i0, floats.length - 1)];
      var b = floats[Math.min(i0 + 1, floats.length - 1)];
      out[i] = a + (b - a) * f;
    }
    return bytesToB64(floatTo16PCM(out));
  }
  function statusColor(st) {
    return st === "DANGER" ? "#ef4444" : st === "WARNING" ? "#f59e0b" : "#10b981";
  }

  // ---------- Shadow DOM UI ----------
  var host = document.createElement("div");
  host.id = "deepshield-host";
  host.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;z-index:2147483647;";
  document.documentElement.appendChild(host);
  var shadow = host.attachShadow({ mode: "open" });

  var CSS =
    ".ds-shield{position:fixed;right:22px;bottom:22px;width:62px;height:62px;border-radius:50%;" +
    "display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:grab;" +
    "background:radial-gradient(circle at 35% 30%,#1e2d47,#0b1220);border:2px solid #10b981;" +
    "color:#e2e8f0;font-family:system-ui,sans-serif;user-select:none;touch-action:none;" +
    "animation:ds-breathe 2.2s ease-in-out infinite;}" +
    "@keyframes ds-breathe{0%,100%{box-shadow:0 0 6px 1px currentColor;}50%{box-shadow:0 0 18px 5px currentColor;}}" +
    ".ds-shield .n{font-size:19px;font-weight:800;line-height:1;}" +
    ".ds-shield .t{font-size:9px;opacity:.75;margin-top:2px;}" +
    ".ds-panel{position:fixed;right:22px;bottom:96px;width:304px;max-height:70vh;overflow-y:auto;" +
    "background:#0b1220;border:1px solid #24365a;border-radius:14px;color:#e2e8f0;" +
    "font-family:system-ui,sans-serif;font-size:13px;padding:12px;display:none;" +
    "box-shadow:0 12px 40px rgba(0,0,0,.6);}" +
    ".ds-panel.open{display:block;}" +
    ".ds-row{display:flex;gap:6px;margin:8px 0;flex-wrap:wrap;}" +
    ".ds-btn{flex:1;min-width:80px;border:1px solid #334155;background:#16233c;color:#e2e8f0;" +
    "border-radius:8px;padding:7px 6px;font-size:12px;cursor:pointer;text-align:center;}" +
    ".ds-btn:hover{border-color:#60a5fa;}" +
    ".ds-btn.primary{background:linear-gradient(135deg,#f43f5e,#f59e0b);border:none;font-weight:700;color:#fff;}" +
    ".ds-btn:disabled{opacity:.45;cursor:default;}" +
    ".ds-score{font-size:30px;font-weight:800;}" +
    ".ds-pill{display:inline-block;border-radius:999px;padding:1px 10px;font-size:11px;font-weight:700;border:1px solid;}" +
    ".ds-alerts{display:flex;flex-direction:column;gap:4px;margin-top:6px;max-height:110px;overflow-y:auto;}" +
    ".ds-alert{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);color:#fca5a5;" +
    "border-radius:6px;padding:4px 8px;font-size:12px;}" +
    ".ds-alert.warn{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.35);color:#fcd34d;}" +
    ".ds-alert.ok{background:rgba(16,185,129,.1);border-color:rgba(16,185,129,.3);color:#6ee7b7;}" +
    ".ds-sub{background:#070d18;border:1px solid #1e2d47;border-radius:8px;padding:6px 8px;" +
    "font-size:12px;color:#bae6fd;min-height:34px;margin-top:6px;}" +
    ".ds-hint{font-size:11px;color:#64748b;margin-top:6px;line-height:1.5;}" +
    ".ds-sec{font-size:11px;color:#94a3b8;margin:10px 0 2px;font-weight:700;letter-spacing:.04em;}" +
    "canvas.ds-spark{width:100%;height:64px;background:#070d18;border:1px solid #1e2d47;border-radius:8px;}";
  var styleEl = document.createElement("style");
  styleEl.textContent = CSS;
  shadow.appendChild(styleEl);

  var shield = el("div", "ds-shield");
  var scoreNum = el("div", "n", "–");
  var shieldTag = el("div", "t", "待機");
  shield.appendChild(scoreNum);
  shield.appendChild(shieldTag);
  shadow.appendChild(shield);

  var panel = el("div", "ds-panel");
  shadow.appendChild(panel);

  var pTitle = el("div", "", "🛡️ DeepShield 即時防護盾");
  pTitle.style.cssText = "font-weight:800;font-size:14px;";
  panel.appendChild(pTitle);
  var pBackend = el("div", "ds-hint", "後端：檢測中…");
  panel.appendChild(pBackend);

  var btnRow = el("div", "ds-row");
  var btnToggle = el("button", "ds-btn", "開始監控此頁面");
  var btnDemo = el("button", "ds-btn", "模擬詐騙直播流");
  btnRow.appendChild(btnToggle);
  btnRow.appendChild(btnDemo);
  panel.appendChild(btnRow);

  var scoreRow = el("div", "");
  scoreRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-top:4px;";
  var bigScore = el("span", "ds-score", "–");
  var pill = el("span", "ds-pill", "待機");
  pill.style.cssText = "border-color:#334155;color:#94a3b8;";
  scoreRow.appendChild(bigScore);
  scoreRow.appendChild(pill);
  panel.appendChild(scoreRow);

  panel.appendChild(el("div", "ds-sec", "即時信任度（最近 15 次）"));
  var spark = document.createElement("canvas");
  spark.className = "ds-spark";
  spark.width = 560;
  spark.height = 128;
  panel.appendChild(spark);

  panel.appendChild(el("div", "ds-sec", "即時警報"));
  var alertBox = el("div", "ds-alerts");
  panel.appendChild(alertBox);

  panel.appendChild(el("div", "ds-sec", "即時字幕"));
  var subBox = el("div", "ds-sub", "（等待監控開始；真實頁面字幕需 STT，Demo 模式內建）");
  panel.appendChild(subBox);

  var sendRow = el("div", "ds-row");
  var btnSend = el("button", "ds-btn primary", "擷取異常片段，送交深度鑑識（開啟模式 A）");
  btnSend.style.cssText += "flex-basis:100%;";
  sendRow.appendChild(btnSend);
  panel.appendChild(sendRow);
  var sendHint = el("div", "ds-hint", "將最近的即時掃描彙整成報告，存入後端並在模式 A 儀表板開啟。");
  panel.appendChild(sendHint);

  // ---------- UI 更新 ----------
  function paintShield() {
    var c = S.scores.length ? statusColor(S.lastStatus) : "#64748b";
    shield.style.borderColor = c;
    shield.style.color = c;
    scoreNum.textContent = S.scores.length ? String(Math.round(S.lastTrust)) : "–";
    shieldTag.textContent = S.monitoring ? (S.demoMode ? "DEMO" : "監控中") : "待機";
    bigScore.textContent = S.scores.length ? String(Math.round(S.lastTrust)) : "–";
    bigScore.style.color = c;
    pill.textContent = S.scores.length ? S.lastStatus : "待機";
    pill.style.borderColor = c;
    pill.style.color = c;
  }
  function paintAlerts() {
    while (alertBox.firstChild) alertBox.removeChild(alertBox.firstChild);
    if (!S.alerts.length) {
      alertBox.appendChild(el("div", "ds-alert ok", S.monitoring ? "目前無異常" : "尚未開始監控"));
      return;
    }
    S.alerts.slice(0, 6).forEach(function (a) {
      var warn = /等待|靜音|建議|僅/.test(a);
      alertBox.appendChild(el("div", "ds-alert" + (warn ? " warn" : ""), a));
    });
  }
  function paintSpark() {
    var ctx = spark.getContext("2d");
    var W = spark.width, H = spark.height;
    ctx.clearRect(0, 0, W, H);
    function y(v) { return H - 8 - (v / 100) * (H - 16); }
    ctx.strokeStyle = "#f59e0b";
    ctx.setLineDash([6, 5]);
    ctx.beginPath(); ctx.moveTo(0, y(60)); ctx.lineTo(W, y(60)); ctx.stroke();
    ctx.strokeStyle = "#ef4444";
    ctx.beginPath(); ctx.moveTo(0, y(40)); ctx.lineTo(W, y(40)); ctx.stroke();
    ctx.setLineDash([]);
    if (S.scores.length < 2) {
      ctx.fillStyle = "#475569";
      ctx.font = "22px system-ui";
      ctx.fillText("等待掃描…", 20, H / 2);
      return;
    }
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 3;
    ctx.beginPath();
    S.scores.forEach(function (v, i) {
      var x = (i / (MAX_SCORES - 1)) * (W - 16) + 8;
      if (i === 0) ctx.moveTo(x, y(v));
      else ctx.lineTo(x, y(v));
    });
    ctx.stroke();
    var last = S.scores[S.scores.length - 1];
    var lx = ((S.scores.length - 1) / (MAX_SCORES - 1)) * (W - 16) + 8;
    ctx.fillStyle = statusColor(S.lastStatus);
    ctx.beginPath();
    ctx.arc(lx, y(last), 7, 0, Math.PI * 2);
    ctx.fill();
  }
  function paintAll() { paintShield(); paintAlerts(); paintSpark(); }

  // ---------- 拖曳 + 展開 ----------
  (function () {
    var sx = 0, sy = 0, ox = 0, oy = 0, moved = 0, dragging = false;
    shield.addEventListener("pointerdown", function (e) {
      dragging = true; moved = 0;
      sx = e.clientX; sy = e.clientY;
      var r = shield.getBoundingClientRect();
      ox = r.left; oy = r.top;
      shield.setPointerCapture(e.pointerId);
      shield.style.animation = "none";
    });
    shield.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
      if (moved > 6) {
        shield.style.left = "auto"; shield.style.top = "auto";
        shield.style.right = "auto"; shield.style.bottom = "auto";
        shield.style.position = "fixed";
        shield.style.left = Math.min(window.innerWidth - 70, Math.max(4, ox + dx)) + "px";
        shield.style.top = Math.min(window.innerHeight - 70, Math.max(4, oy + dy)) + "px";
      }
    });
    shield.addEventListener("pointerup", function () {
      dragging = false;
      shield.style.animation = "";
      if (moved <= 6) panel.classList.toggle("open");
    });
  })();

  // ---------- 影音擷取（全降級、絕不崩潰） ----------
  function visibleVideos() {
    try {
      var vs = Array.prototype.slice.call(document.querySelectorAll("video"));
      return vs
        .filter(function (v) {
          try {
            var r = v.getBoundingClientRect();
            return r.width > 120 && r.height > 80 && v.readyState >= 2 && !v.ended;
          } catch (e) { return false; }
        })
        .sort(function (a, b) {
          var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
          return rb.width * rb.height - ra.width * ra.height;
        })
        .slice(0, 2);
    } catch (e) { return []; }
  }

  var frameCanvas = document.createElement("canvas");
  function grabFrame(video) {
    try {
      var vw = video.videoWidth || 320, vh = video.videoHeight || 180;
      var scale = Math.min(1, 320 / vw);
      frameCanvas.width = Math.max(2, Math.floor(vw * scale));
      frameCanvas.height = Math.max(2, Math.floor(vh * scale));
      var ctx = frameCanvas.getContext("2d");
      ctx.drawImage(video, 0, 0, frameCanvas.width, frameCanvas.height);
      var url = frameCanvas.toDataURL("image/jpeg", 0.7);
      var i = url.indexOf(",");
      return i > 0 ? url.slice(i + 1) : "";
    } catch (e) { return ""; } // canvas 被 CORS 污染 → 回傳空字串降級
  }

  function ensureTap(video) {
    var tap = S.taps.get(video);
    if (tap) return tap;
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      var ctx = new AC();
      if (ctx.state === "suspended") { ctx.resume().catch(function () {}); }
      var src = ctx.createMediaElementSource(video);
      var analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      src.connect(analyser);
      analyser.connect(ctx.destination); // 保持原本可聽
      tap = { ctx: ctx, analyser: analyser };
      S.taps.set(video, tap);
      // 連續收集時域樣本（跨域靜音時讀到全零，後端會判靜音略過）
      var buf = new Float32Array(analyser.fftSize);
      setInterval(function () {
        try {
          analyser.getFloatTimeDomainData(buf);
          for (var i = 0; i < buf.length; i++) S.audioRing.push(buf[i]);
          if (S.audioRing.length > 96000) S.audioRing.splice(0, S.audioRing.length - 96000);
          S.audioSR = ctx.sampleRate || 48000;
        } catch (e) { /* 忽略單次讀取失敗 */ }
      }, 120);
      return tap;
    } catch (e) { return null; } // 同一元素重複 tap / 不支援 → 無音訊降級
  }

  function snapshotAudio() {
    try {
      if (S.audioRing.length < 2048) return "";
      var take = S.audioRing.slice(-32768);
      var sum = 0;
      for (var i = 0; i < take.length; i++) sum += take[i] * take[i];
      var rms = Math.sqrt(sum / take.length);
      if (rms < 1e-4) { S.audioNote = "音訊接近靜音（可能受 CORS 保護），僅用影像訊號評分"; return ""; }
      S.audioNote = "";
      return resampleTo16k(take, S.audioSR);
    } catch (e) { return ""; }
  }

  // ---------- Demo 串流合成器（任何頁面都能展示 DANGER） ----------
  var demoCanvas = document.createElement("canvas");
  demoCanvas.width = 320; demoCanvas.height = 180;
  function demoFrame(variant) {
    var ctx = demoCanvas.getContext("2d");
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, 320, 180);
    ctx.fillStyle = "#7f1d1d";
    ctx.beginPath(); ctx.arc(160 + (variant ? 8 : -8), 92, 52, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fca5a5";
    ctx.beginPath(); ctx.arc(142, 82, 7, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(178, 82, 7, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#fca5a5"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(160, 100, 20, 0.15 * Math.PI, 0.85 * Math.PI); ctx.stroke();
    if (variant) { // 閃爍破綻
      ctx.fillStyle = "rgba(239,68,68,.25)";
      ctx.fillRect(60, 30, 200, 120);
    }
    ctx.fillStyle = "#ef4444";
    ctx.beginPath(); ctx.arc(26, 24, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 15px system-ui";
    ctx.fillText("LIVE 投資講座", 42, 29);
    ctx.fillStyle = "#fbbf24";
    ctx.font = "13px system-ui";
    ctx.fillText("保證獲利 · 飆股內線", 42, 160);
    var url = demoCanvas.toDataURL("image/jpeg", 0.7);
    var i = url.indexOf(",");
    return i > 0 ? url.slice(i + 1) : "";
  }
  function demoAudio() {
    var n = 32000, sr = 16000, out = new Float32Array(n);
    var seed = (S.demoTick + 1) * 12345;
    function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
    var f0 = 130 + (S.demoTick % 3) * 25;
    for (var i = 0; i < n; i++) {
      var t = i / sr;
      var gate = (Math.sin(2 * Math.PI * 4 * t) > -0.2) ? 1 : 0.05;
      out[i] = gate * 0.5 * (Math.sin(2 * Math.PI * f0 * t) * 0.6 +
        Math.sin(2 * Math.PI * f0 * 2 * t) * 0.25 +
        Math.sin(2 * Math.PI * f0 * 3 * t) * 0.15) + (rnd() - 0.5) * 0.03;
    }
    return resampleTo16k(Array.prototype.slice.call(out), sr);
  }

  // ---------- WebSocket ----------
  function connectWS() {
    if (S.ws && (S.ws.readyState === WebSocket.OPEN || S.ws.readyState === WebSocket.CONNECTING)) return;
    try {
      S.ws = new WebSocket(WS_URL);
    } catch (e) { scheduleReconnect(); return; }
    S.ws.onopen = function () { pBackend.textContent = "後端：已連線（每 2 秒快掃）"; };
    S.ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      S.lastTrust = typeof msg.trust_score === "number" ? msg.trust_score : 100;
      S.lastStatus = msg.status || "SAFE";
      S.alerts = Array.isArray(msg.alerts) ? msg.alerts : [];
      S.transcript = msg.transcript_snippet || S.transcript;
      S.scores.push(S.lastTrust);
      if (S.scores.length > MAX_SCORES) S.scores.shift();
      S.history.push({
        t: typeof msg.timestamp === "number" ? msg.timestamp : (Date.now() - S.t0) / 1000,
        trust: S.lastTrust, status: S.lastStatus,
        alerts: S.alerts.slice(), snippet: S.transcript,
      });
      if (S.transcript) subBox.textContent = S.transcript;
      paintAll();
    };
    S.ws.onclose = function () {
      pBackend.textContent = "後端：連線中斷（重試中…請確認黑窗開著）";
      scheduleReconnect();
    };
    S.ws.onerror = function () {
      try { S.ws.close(); } catch (e) {}
    };
  }
  var reconnectTimer = null;
  function scheduleReconnect() {
    if (!S.wsWanted || reconnectTimer) return;
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      if (S.wsWanted) connectWS();
    }, 3000);
  }

  function sendTick() {
    if (!S.monitoring) return;
    var now = (Date.now() - S.t0) / 1000;
    var frames = [];
    var audioB64 = "";
    var snippet = "";
    try {
      if (S.demoMode) {
        frames = [demoFrame(false), demoFrame(true)];
        audioB64 = demoAudio();
        snippet = DEMO_LINES[S.demoTick % DEMO_LINES.length];
        S.demoTick++;
        S.videoNote = "";
        S.audioNote = "";
      } else {
        var vids = visibleVideos();
        if (vids.length === 0) {
          S.videoNote = "未發現可監控的影片（播放影片後自動開始，或用「模擬詐騙直播流」）";
          pBackend.textContent = "後端：" + (S.ws && S.ws.readyState === 1 ? "已連線" : "待連線") + " — " + S.videoNote;
          return; // 沒有訊號就不送，避免洗出無意義的 SAFE
        }
        S.videoNote = "";
        vids.forEach(function (v) {
          var f = grabFrame(v);
          if (f) frames.push(f);
          ensureTap(v);
        });
        audioB64 = snapshotAudio();
      }
    } catch (e) {
      frames = []; audioB64 = "";
    }
    if (S.ws && S.ws.readyState === WebSocket.OPEN) {
      try {
        S.ws.send(JSON.stringify({
          timestamp: Math.round(now * 10) / 10,
          audio_b64: audioB64,
          frames_b64: frames,
          transcript_snippet: snippet,
        }));
      } catch (e) { /* 下輪重試 */ }
    } else {
      connectWS();
    }
  }

  // ---------- 控制 ----------
  function setMonitoring(on) {
    S.monitoring = on;
    if (on) {
      S.t0 = S.t0 || Date.now();
      S.wsWanted = true;
      connectWS();
      sendTick();
      S.timer = setInterval(sendTick, TICK_MS);
      btnToggle.textContent = "停止監控";
      if (!S.demoMode) subBox.textContent = "監控中…（真實頁面字幕需 STT，警報即時顯示於上方）";
    } else {
      S.wsWanted = false;
      if (S.timer) { clearInterval(S.timer); S.timer = null; }
      try { if (S.ws) S.ws.close(); } catch (e) {}
      S.ws = null;
      btnToggle.textContent = "開始監控此頁面";
      pBackend.textContent = "後端：已停止";
    }
    paintAll();
  }
  btnToggle.addEventListener("click", function () { setMonitoring(!S.monitoring); });
  btnDemo.addEventListener("click", function () {
    S.demoMode = true;
    S.demoTick = 0;
    if (!S.monitoring) setMonitoring(true);
    subBox.textContent = "Demo 串流放送中…";
    paintAll();
  });

  // ---------- 一鍵送交模式 A ----------
  function alertType(a) {
    if (/高頻|音訊|靜音/.test(a)) return "AUDIO_ANOMALY";
    if (/臉部|換臉|平滑/.test(a)) return "FACE_FLICKER";
    if (/詐騙詞彙/.test(a)) return "SCAM_KEYWORD";
    return "AUDIO_ANOMALY";
  }
  function extractKeyword(a) {
    var m = /[詞彙][:：]\s*(.+?)\s*$/.exec(a);
    return m ? m[1].replace(/[）)]*$/, "") : "";
  }
  function buildReport() {
    var hist = S.history.slice(-15);
    if (!hist.length) return null;
    var latest = hist[hist.length - 1];
    var fake = Math.round((100 - latest.trust) * 10) / 10;
    var trust = Math.round(latest.trust * 10) / 10;
    var status = latest.status;
    var end = Math.round((latest.t + 2) * 10) / 10;
    var timeline = [];
    var segments = [];
    var spans = [];
    hist.forEach(function (h) {
      if (h.snippet) segments.push({ start: h.t, end: Math.round((h.t + 2) * 10) / 10, text: h.snippet });
      (h.alerts || []).forEach(function (a) {
        var type = alertType(a);
        timeline.push({ start: h.t, end: Math.round((h.t + 2) * 10) / 10, type: type, description: a });
        if (type === "SCAM_KEYWORD" && h.snippet) {
          var kw = extractKeyword(a);
          if (kw && h.snippet.indexOf(kw) >= 0) {
            var idx = h.snippet.indexOf(kw);
            var frac0 = idx / h.snippet.length, frac1 = (idx + kw.length) / h.snippet.length;
            spans.push({
              start: Math.round((h.t + frac0 * 2) * 100) / 100,
              end: Math.round((h.t + frac1 * 2) * 100) / 100,
              text: kw, keyword: kw, category: "即時攔截",
            });
          }
        }
      });
    });
    timeline.sort(function (a, b) { return a.start - b.start; });
    var note = "即時快掃彙整（2 秒窗輕量掃描，非深度鑑識完整四維；數值來自最近 15 次 WS 評分）";
    return {
      fake_probability: fake,
      trust_score: trust,
      status: status,
      duration: end,
      filename: "realtime-" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") + "（外掛攔截）",
      dimensions: {
        audio: { risk: fake, level: status, note: note, anomalies: [], spectrogram_b64: "", subscores: {} },
        visual: { risk: fake, level: status, note: note, anomalies: [], heatmap_b64: "", subscores: {} },
        av_sync: { risk: 0, level: "SAFE", note: "即時模式不做唇同步深度比對", mismatches: [] },
        semantic: {
          risk: spans.length ? fake : 0, level: status, hit_count: spans.length,
          stt_available: true, transcript: segments,
          full_text: segments.map(function (s) { return s.text; }).join(""),
          spans: spans,
          hits: spans.map(function (s) { return { keyword: s.keyword, category: s.category, start: s.start, end: s.end }; }),
        },
      },
      timeline: timeline,
      skipped_dimensions: ["avsync"],
    };
  }

  btnSend.addEventListener("click", function () {
    if (S.sessionBusy) return;
    var report = buildReport();
    if (!report) {
      sendHint.textContent = "還沒有任何掃描紀錄：請先「開始監控」或播放「模擬詐騙直播流」累積幾次評分再送交。";
      return;
    }
    S.sessionBusy = true;
    btnSend.disabled = true;
    btnSend.textContent = "送交中…";
    var sid = "ext-" + Date.now().toString(36);
    var label = "外掛攔截：" + (document.title || location.hostname).slice(0, 40);
    var payload = { report: report, mediaKind: "video", label: label };
    function openDash() {
      var url = DASHBOARD + "/?from=extension&session_id=" + encodeURIComponent(sid);
      try {
        chrome.runtime.sendMessage({ type: "OPEN_DASHBOARD", url: url }, function (res) {
          if (!res || !res.ok) window.open(url, "_blank");
          resetSendBtn();
        });
      } catch (e) {
        try { window.open(url, "_blank"); } catch (e2) {}
        resetSendBtn();
      }
    }
    function resetSendBtn() {
      S.sessionBusy = false;
      btnSend.disabled = false;
      btnSend.textContent = "擷取異常片段，送交深度鑑識（開啟模式 A）";
    }
    // 解法 A：後端暫存（主）＋ 解法 B：chrome.storage 備份（bridge 會搬運）
    try {
      var backup = {};
      backup["deepshield:session:" + sid] = payload;
      chrome.storage.local.set(backup, function () {});
    } catch (e) {}
    fetch(API_BASE + "/api/v1/session/" + encodeURIComponent(sid), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("http " + r.status);
        sendHint.textContent = "已送交！模式 A 分頁開啟後會自動載入本次攔截報告。";
        openDash();
      })
      .catch(function () {
        sendHint.textContent = "後端未啟動（連不上 " + API_BASE + "）：請先雙擊桌面「DeepShield 啟動」再重試。";
        resetSendBtn();
      });
  });

  // ---------- 後端存活探測（面板開啟時） ----------
  function probeBackend() {
    fetch(API_BASE + "/api/v1/health", { method: "GET" })
      .then(function (r) {
        if (r.ok) pBackend.textContent = S.monitoring ? pBackend.textContent : "後端：就緒（可開始監控）";
        else pBackend.textContent = "後端：異常（請確認黑窗開著）";
      })
      .catch(function () {
        pBackend.textContent = "後端：未連線（請先雙擊桌面「DeepShield 啟動」）";
      });
  }
  // 展開面板時探測一次
  new MutationObserver(function () {
    if (panel.classList.contains("open")) probeBackend();
  }).observe(panel, { attributes: true, attributeFilter: ["class"] });

  paintAll();
  console.log("[DeepShield] realtime shield ready");
})();
