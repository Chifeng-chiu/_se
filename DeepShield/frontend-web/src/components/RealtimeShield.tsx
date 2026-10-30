import { useEffect, useRef, useState } from "react";
import { Camera, Film, FlaskConical, OctagonAlert, Play, Square } from "lucide-react";
import { WS_URL, type RealtimeResult } from "../api";
import type { DeepReport, Verdict } from "../types";

type SourceKind = "live" | "demovideo" | "sim";

const DEMO_LINES = [
  "現在加入老師的群組，保證獲利，飆股內線免費送",
  "名額只剩最後三十位，趕快匯款到監管帳戶卡位",
  "這件事不能告訴別人，立刻轉帳，驗證碼先給我",
];

const DEMO_VIDEO = "/demo/celebrity-investment-scam.mp4";
const TICK_MS = 2000;
const MAX_SCORES = 15;

export interface RealtimePoint {
  t: number;
  trust: number;
  status: Verdict;
  alerts: string[];
  snippet: string;
}

function statusColor(s: Verdict | string): string {
  return s === "DANGER" ? "#EF4444" : s === "WARNING" ? "#F59E0B" : "#10B981";
}

/** Float32 mono → 16k WAV base64 (後端 soundfile 可直接解) */
function encodeWavB64(samples: Float32Array, fromSR: number): string {
  if (samples.length === 0) return "";
  const toSR = 16000;
  const ratio = fromSR / toSR;
  const n = Math.max(1, Math.floor(samples.length / ratio));
  const data = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const f = pos - i0;
    const a = samples[Math.min(i0, samples.length - 1)];
    const b = samples[Math.min(i0 + 1, samples.length - 1)];
    data[i] = a + (b - a) * f;
  }
  const buf = new ArrayBuffer(44 + n * 2);
  const dv = new DataView(buf);
  const writeStr = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  dv.setUint32(4, 36 + n * 2, true);
  writeStr(8, "WAVEfmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true);
  dv.setUint16(22, 1, true);
  dv.setUint32(24, toSR, true);
  dv.setUint32(28, toSR * 2, true);
  dv.setUint16(32, 2, true);
  dv.setUint16(34, 16, true);
  writeStr(36, "data");
  dv.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    const v = Math.max(-1, Math.min(1, data[i]));
    dv.setInt16(44 + i * 2, v < 0 ? v * 32768 : v * 32767, true);
  }
  const bytes = new Uint8Array(buf);
  let s = "";
  const CH = 8192;
  for (let i = 0; i < bytes.length; i += CH) {
    s += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + CH)));
  }
  return btoa(s);
}

function grabVideoFrame(video: HTMLVideoElement | null): string {
  if (!video || video.readyState < 2 || video.videoWidth === 0) return "";
  try {
    const c = document.createElement("canvas");
    const scale = Math.min(1, 320 / video.videoWidth);
    c.width = Math.max(2, Math.floor(video.videoWidth * scale));
    c.height = Math.max(2, Math.floor(video.videoHeight * scale));
    const ctx = c.getContext("2d");
    if (!ctx) return "";
    ctx.drawImage(video, 0, 0, c.width, c.height);
    const url = c.toDataURL("image/jpeg", 0.7);
    const i = url.indexOf(",");
    return i > 0 ? url.slice(i + 1) : "";
  } catch {
    return ""; // CORS 污染等 → 降級空幀
  }
}

/** 模擬詐騙直播合成幀 (無需任何媒體，任何頁面都能出 DANGER) */
function synthDemoFrame(variant: boolean): string {
  const c = document.createElement("canvas");
  c.width = 320;
  c.height = 180;
  const ctx = c.getContext("2d");
  if (!ctx) return "";
  ctx.fillStyle = "#0B1220";
  ctx.fillRect(0, 0, 320, 180);
  ctx.fillStyle = "#7F1D1D";
  ctx.beginPath();
  ctx.arc(160 + (variant ? 8 : -8), 92, 52, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#FCA5A5";
  ctx.beginPath(); ctx.arc(142, 82, 7, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(178, 82, 7, 0, Math.PI * 2); ctx.fill();
  if (variant) {
    ctx.fillStyle = "rgba(239,68,68,.25)";
    ctx.fillRect(60, 30, 200, 120);
  }
  ctx.fillStyle = "#EF4444";
  ctx.beginPath(); ctx.arc(26, 24, 8, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#FFF";
  ctx.font = "bold 15px system-ui";
  ctx.fillText("LIVE 投資講座", 42, 29);
  ctx.fillStyle = "#FBBF24";
  ctx.font = "13px system-ui";
  ctx.fillText("保證獲利 · 飆股內線", 42, 160);
  const url = c.toDataURL("image/jpeg", 0.7);
  const i = url.indexOf(",");
  return i > 0 ? url.slice(i + 1) : "";
}

function buildReportFromHistory(history: RealtimePoint[]): DeepReport | null {
  if (history.length === 0) return null;
  const latest = history[history.length - 1];
  const fake = Math.round((100 - latest.trust) * 10) / 10;
  const trust = Math.round(latest.trust * 10) / 10;
  const timeline = history.flatMap((h) =>
    h.alerts.map((a) => ({
      start: h.t,
      end: Math.round((h.t + 2) * 10) / 10,
      type: /詐騙|詞彙|關鍵|保證|匯款/.test(a) ? "SCAM_KEYWORD" : "AUDIO_ANOMALY",
      description: a,
    }))
  );
  const segments = history
    .filter((h) => h.snippet)
    .map((h) => ({ start: h.t, end: Math.round((h.t + 2) * 10) / 10, text: h.snippet }));
  const kws = ["保證獲利", "飆股", "匯款", "監管帳戶", "驗證碼", "急用錢", "老師"];
  const spans = segments.flatMap((s) => {
    const found = kws.filter((k) => s.text.includes(k));
    return found.map((k) => {
      const idx = s.text.indexOf(k);
      const frac0 = idx / Math.max(1, s.text.length);
      const frac1 = (idx + k.length) / Math.max(1, s.text.length);
      return {
        start: Math.round((s.start + frac0 * 2) * 100) / 100,
        end: Math.round((s.start + frac1 * 2) * 100) / 100,
        text: k,
        keyword: k,
        category: "即時攔截",
      };
    });
  });
  const note = "網頁即時快掃彙整（2 秒窗輕量掃描，非深度鑑識完整四維）";
  return {
    fake_probability: fake,
    trust_score: trust,
    status: latest.status,
    duration: latest.t + 2,
    filename: `realtime-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}（即時攔截）`,
    analyzed_at: new Date().toISOString(),
    dimensions: {
      audio: { risk: fake, level: latest.status, note, anomalies: [], spectrogram_b64: "", subscores: {} },
      visual: { risk: fake, level: latest.status, note, anomalies: [], heatmap_b64: "", subscores: {} },
      av_sync: { risk: 0, level: "SAFE", note: "即時模式不做唇同步深度比對", mismatches: [] },
      semantic: {
        risk: spans.length ? fake : 0,
        level: latest.status,
        hit_count: spans.length,
        stt_available: true,
        transcript: segments,
        full_text: segments.map((s) => s.text).join(""),
        spans,
        hits: spans.map((s) => ({ keyword: s.keyword, category: s.category, start: s.start, end: s.end })),
      },
    },
    timeline,
    skipped_dimensions: ["avsync"],
  };
}

export default function RealtimeShield({
  onSendToForensics,
}: {
  onSendToForensics: (report: DeepReport, mediaUrl: string | null, label: string) => void;
}) {
  const [source, setSource] = useState<SourceKind>("sim");
  const [monitoring, setMonitoring] = useState(false);
  const [wsState, setWsState] = useState<"idle" | "connecting" | "open" | "error">("idle");
  const [scores, setScores] = useState<number[]>([]);
  const [lastStatus, setLastStatus] = useState<Verdict>("SAFE");
  const [lastTrust, setLastTrust] = useState(100);
  const [alerts, setAlerts] = useState<string[]>(["尚未開始監控"]);
  const [subs, setSubs] = useState<Array<{ t: number; text: string }>>([]);
  const [hint, setHint] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<number | null>(null);
  const t0Ref = useRef(0);
  const tickRef = useRef(0);
  const historyRef = useRef<RealtimePoint[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const ringRef = useRef<Float32Array>(new Float32Array(0));
  const ringSRRef = useRef(48000);
  const snippetRef = useRef("");
  const recogRef = useRef<{ stop: () => void } | null>(null);
  const historyKey = useRef(0);
  const [, forceTick] = useState(0);

  // 即時字幕：Web Speech API (僅 live 模式，有就加分、沒有也不崩)
  function startSpeech() {
    try {
      const SR =
        (window as unknown as { SpeechRecognition?: new () => unknown; webkitSpeechRecognition?: new () => unknown })
          .SpeechRecognition ??
        (window as unknown as { webkitSpeechRecognition?: new () => unknown }).webkitSpeechRecognition;
      if (!SR) return;
      const rec = new (SR as new () => {
        lang: string;
        continuous: boolean;
        interimResults: boolean;
        onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
        start: () => void;
        stop: () => void;
      })();
      rec.lang = "zh-TW";
      rec.continuous = true;
      rec.interimResults = true;
      rec.onresult = (e) => {
        try {
          const last = e.results[e.results.length - 1];
          const txt = last[0]?.transcript ?? "";
          if (txt) snippetRef.current = txt.slice(-60);
        } catch {
          /* 忽略單次辨識失敗 */
        }
      };
      rec.start();
      recogRef.current = rec;
    } catch {
      /* 不支援語音辨識 → 直接降級 */
    }
  }
  function stopSpeech() {
    try {
      recogRef.current?.stop();
    } catch {
      /* ignore */
    }
    recogRef.current = null;
  }

  async function ensureLiveMedia(): Promise<boolean> {
    if (streamRef.current) return true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      streamRef.current = stream;
      const v = videoRef.current;
      if (v) {
        v.srcObject = stream;
        await v.play().catch(() => undefined);
      }
      // 音訊累積
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (AC) {
        const ctx = new AC();
        audioCtxRef.current = ctx;
        ringSRRef.current = ctx.sampleRate || 48000;
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(4096, 1, 1);
        procRef.current = proc;
        proc.onaudioprocess = (e) => {
          const ch = e.inputBuffer.getChannelData(0);
          const prev = ringRef.current;
          const next = new Float32Array(Math.min(96000, prev.length + ch.length));
          next.set(prev.slice(Math.max(0, prev.length + ch.length - 96000)), 0);
          next.set(ch.slice(0, next.length - Math.min(prev.length, next.length - 0)), Math.min(prev.length, next.length));
          // 簡化：保留最近 96k
          const combined = new Float32Array([...prev.slice(-(96000 - ch.length)), ...ch].slice(-96000));
          ringRef.current = combined;
        };
        src.connect(proc);
        proc.connect(ctx.destination);
      }
      return true;
    } catch {
      setHint("無法開啟麥克風/鏡頭（請允許瀏覽器權限），可改用內建測試影片或模擬直播流。");
      return false;
    }
  }

  function stopLiveMedia() {
    stopSpeech();
    try {
      procRef.current?.disconnect();
    } catch {
      /* ignore */
    }
    procRef.current = null;
    try {
      void audioCtxRef.current?.close();
    } catch {
      /* ignore */
    }
    audioCtxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => {
      try {
        t.stop();
      } catch {
        /* ignore */
      }
    });
    streamRef.current = null;
    ringRef.current = new Float32Array(0);
    if (videoRef.current && source === "live") videoRef.current.srcObject = null;
  }

  function sendTick() {
    const ws = wsRef.current;
    const now = (Date.now() - t0Ref.current) / 1000;
    let audioB64 = "";
    let frames: string[] = [];
    let snippet = "";
    if (source === "sim") {
      frames = [synthDemoFrame(tickRef.current % 2 === 0), synthDemoFrame(tickRef.current % 2 === 1)];
      snippet = DEMO_LINES[tickRef.current % DEMO_LINES.length];
    } else if (source === "demovideo") {
      const f = grabVideoFrame(videoRef.current);
      if (f) frames = [f];
      const vt = videoRef.current?.currentTime ?? tickRef.current * 2;
      snippet = DEMO_LINES[Math.floor(vt / 2) % DEMO_LINES.length];
    } else {
      const f = grabVideoFrame(videoRef.current);
      if (f) frames = [f];
      // 音訊：取最近 2 秒
      const ring = ringRef.current;
      if (ring.length > 8000) {
        const take = ring.slice(-32000);
        let sum = 0;
        for (let i = 0; i < take.length; i++) sum += take[i] * take[i];
        const rms = Math.sqrt(sum / take.length);
        if (rms >= 1e-4) audioB64 = encodeWavB64(take, ringSRRef.current);
      }
      snippet = snippetRef.current;
    }
    tickRef.current++;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ timestamp: Math.round(now * 10) / 10, audio_b64: audioB64, frames_b64: frames, transcript_snippet: snippet }));
      } catch {
        /* 下輪重試 */
      }
    }
  }

  async function start() {
    setHint(null);
    if (source === "live") {
      const ok = await ensureLiveMedia();
      if (!ok) return;
      startSpeech();
    }
    if (source === "demovideo") {
      // 確保影片播放（有聲音也沒關係，視覺+語意即足夠出分）
      try {
        await videoRef.current?.play().catch(() => undefined);
      } catch {
        /* ignore */
      }
    }
    t0Ref.current = t0Ref.current || Date.now();
    historyKey.current++;
    setMonitoring(true);
    setWsState("connecting");
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setWsState("open");
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as RealtimeResult;
          const trust = typeof msg.trust_score === "number" ? msg.trust_score : 100;
          const status = (msg.status ?? "SAFE") as Verdict;
          const al = Array.isArray(msg.alerts) ? msg.alerts : [];
          const snip = msg.transcript_snippet ?? "";
          const t = typeof msg.timestamp === "number" ? msg.timestamp : (Date.now() - t0Ref.current) / 1000;
          setLastTrust(trust);
          setLastStatus(status);
          setAlerts(al.length ? al : ["目前無異常"]);
          setScores((prev) => [...prev.slice(-(MAX_SCORES - 1)), trust]);
          historyRef.current.push({ t, trust, status, alerts: al, snippet: snip });
          if (historyRef.current.length > 60) historyRef.current = historyRef.current.slice(-60);
          if (snip) setSubs((prev) => [...prev.slice(-19), { t, text: snip }]);
          forceTick((x) => x + 1);
        } catch {
          /* 單幀解析失敗略過 */
        }
      };
      ws.onclose = () => {
        setWsState((s) => (s === "open" ? "error" : s));
      };
      ws.onerror = () => setWsState("error");
    } catch {
      setWsState("error");
      setHint("連不上後端 WS，請確認黑窗開著（ws://localhost:8000）。");
      setMonitoring(false);
      return;
    }
    timerRef.current = window.setInterval(sendTick, TICK_MS);
    // 立刻先送一次
    window.setTimeout(sendTick, 300);
  }

  function stop() {
    setMonitoring(false);
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    try {
      wsRef.current?.close();
    } catch {
      /* ignore */
    }
    wsRef.current = null;
    setWsState("idle");
    if (source === "live") stopLiveMedia();
    try {
      videoRef.current?.pause();
    } catch {
      /* ignore */
    }
  }

  // 切換來源時先停播，避免殘留串流
  function switchSource(k: SourceKind) {
    if (monitoring) stop();
    snippetRef.current = "";
    setSource(k);
    setHint(null);
  }

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      stopSpeech();
      streamRef.current?.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* ignore */
        }
      });
    },
    []
  );

  const col = statusColor(lastStatus);
  const pts = scores
    .map((v, i) => {
      const x = (i / Math.max(1, MAX_SCORES - 1)) * 280 + 10;
      const y = 64 - 6 - (v / 100) * 52;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const historyLen = historyRef.current.length;

  function handleHandoff() {
    const report = buildReportFromHistory(historyRef.current);
    if (!report) {
      setHint("還沒有任何掃描紀錄：請先開始監控累積幾次評分再送交。");
      return;
    }
    onSendToForensics(report, source === "demovideo" ? DEMO_VIDEO : null, `即時攔截送檢（${report.status}，${historyLen} 次快掃）`);
  }

  return (
    <div className="space-y-4">
      {/* 來源選擇 */}
      <div className="flex flex-wrap gap-2">
        {(
          [
            { k: "live", icon: <Camera size={15} />, t: "本機麥克風 / 鏡頭實測" },
            { k: "demovideo", icon: <Film size={15} />, t: "播放內建測試影片" },
            { k: "sim", icon: <FlaskConical size={15} />, t: "模擬詐騙直播流" },
          ] as Array<{ k: SourceKind; icon: React.ReactNode; t: string }>
        ).map((o) => (
          <button
            key={o.k}
            onClick={() => switchSource(o.k)}
            disabled={monitoring}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-bold transition disabled:opacity-40 ${
              source === o.k ? "border-sky-400 bg-sky-500/15 text-sky-200" : "border-line bg-panel text-slate-400 hover:border-slate-500"
            }`}
          >
            {o.icon}
            {o.t}
          </button>
        ))}
        <div className="ml-auto flex gap-2">
          {!monitoring ? (
            <button
              onClick={() => void start()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 px-5 py-2 text-sm font-bold text-white hover:brightness-110"
            >
              <Play size={16} /> 開始即時監控
            </button>
          ) : (
            <button
              onClick={stop}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-700 px-5 py-2 text-sm font-bold text-white hover:bg-slate-600"
            >
              <Square size={16} /> 停止監控
            </button>
          )}
        </div>
      </div>

      {hint && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-200">{hint}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 左：監控播放器 */}
        <div className="rounded-xl border border-line bg-panel p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-300">
            即時監控播放器
            <span className="ml-2 text-xs font-normal text-slate-500">
              {source === "live" ? "需允許鏡頭/麥克風權限" : source === "demovideo" ? "內建 8 秒詐騙範例循環播放" : "無需媒體，一鍵出 DANGER"}
            </span>
          </h3>
          {source === "sim" ? (
            <div className="flex h-[240px] flex-col items-center justify-center gap-2 rounded-lg bg-black text-center">
              <p className="text-4xl">📡</p>
              <p className="text-sm text-slate-300">模擬詐騙直播流放送中</p>
              <p className="font-mono text-xs text-slate-500">保證獲利 · 飆股內線 · 趕快匯款（每 2s 一句）</p>
            </div>
          ) : (
            <video
              ref={videoRef}
              src={source === "demovideo" ? DEMO_VIDEO : undefined}
              controls={source === "demovideo"}
              muted={source === "demovideo"}
              loop={source === "demovideo"}
              playsInline
              className="max-h-[240px] w-full rounded-lg bg-black"
            />
          )}
          <p className="mt-2 font-mono text-xs text-slate-500">
            WS：{WS_URL} · 狀態：
            {wsState === "open" ? "已連線（每 2s 快掃）" : wsState === "connecting" ? "連線中…" : wsState === "error" ? "連線失敗（檢查黑窗）" : "待機"}
          </p>
        </div>

        {/* 右：盾牌 + 曲線 + 警報 */}
        <div className="rounded-xl border border-line bg-panel p-4">
          <div className="flex items-center gap-4">
            <div
              className={`flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-full border-2 ${lastStatus === "DANGER" ? "danger-glow" : ""}`}
              style={{ borderColor: col, color: col }}
            >
              <span className="text-2xl font-extrabold leading-none">{scores.length ? Math.round(lastTrust) : "–"}</span>
              <span className="mt-0.5 text-[10px]">{monitoring ? lastStatus : "待機"}</span>
            </div>
            <div className="flex-1">
              <p className="text-sm text-slate-400">
                即時信任度 <span className="font-mono font-bold" style={{ color: col }}>{lastTrust.toFixed(1)}</span>
                <span className="text-slate-600"> / 100</span>
              </p>
              <svg viewBox="0 0 300 70" className="mt-1 w-full rounded-lg border border-line bg-ink" style={{ height: 70 }}>
                <line x1="0" y1={70 - 6 - 0.6 * 52} x2="300" y2={70 - 6 - 0.6 * 52} stroke="#F59E0B" strokeDasharray="5 4" strokeWidth="1" />
                <line x1="0" y1={70 - 6 - 0.4 * 52} x2="300" y2={70 - 6 - 0.4 * 52} stroke="#EF4444" strokeDasharray="5 4" strokeWidth="1" />
                {scores.length >= 2 ? (
                  <polyline points={pts} fill="none" stroke="#38BDF8" strokeWidth="2.5" />
                ) : (
                  <text x="12" y="38" fill="#475569" fontSize="12">等待掃描…</text>
                )}
              </svg>
            </div>
          </div>
          <h4 className="mt-3 text-xs font-bold tracking-wide text-slate-400">即時警報標籤</h4>
          <div className="mt-1 flex max-h-24 flex-col gap-1 overflow-y-auto">
            {alerts.map((a, i) => (
              <span
                key={i}
                className={`rounded-lg border px-2.5 py-1 text-xs ${
                  lastStatus === "DANGER"
                    ? "border-red-500/40 bg-red-500/10 text-red-200"
                    : lastStatus === "WARNING"
                      ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                      : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                }`}
              >
                {a}
              </span>
            ))}
          </div>
          <h4 className="mt-3 text-xs font-bold tracking-wide text-slate-400">即時字幕流</h4>
          <div className="mt-1 max-h-24 overflow-y-auto rounded-lg bg-ink px-3 py-2 text-sm leading-relaxed text-sky-200">
            {subs.length === 0 ? (
              <span className="text-xs text-slate-500">（監控開始後字幕會顯示在這裡；live 模式可用瀏覽器語音辨識，真實 STT）</span>
            ) : (
              subs.slice(-6).map((s, i) => (
                <p key={i}>
                  <span className="mr-2 font-mono text-xs text-sky-400/80">[{s.t.toFixed(1)}s]</span>
                  {s.text}
                </p>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 送交模式 A */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-3">
        <OctagonAlert size={18} className="text-rose-300" />
        <span className="text-sm text-slate-300">
          已累積 <span className="font-mono font-bold text-white">{historyLen}</span> 次快掃
          {lastStatus === "DANGER" && <span className="ml-2 font-bold text-red-300">紅燈！建議立即送交深度鑑識</span>}
        </span>
        <button
          onClick={handleHandoff}
          disabled={historyLen === 0}
          className="ml-auto inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-rose-500 to-orange-500 px-5 py-2.5 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-40"
        >
          🚨 擷取異常片段，送交模式 A 深度鑑識
        </button>
      </div>
    </div>
  );
}
