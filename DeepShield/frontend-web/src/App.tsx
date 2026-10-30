import { useEffect, useRef, useState } from "react";
import { Film, Link2, Loader2, Mic, Radio, RotateCcw, Shield, Sparkles, X } from "lucide-react";
import { analyzeFile, analyzeUrl, API_BASE, checkHealth } from "./api";
import { demoCelebrity, demoVoice } from "./mockDemos";
import type { DeepReport, LoadedCase, MediaKind } from "./types";
import StatusBadge from "./components/StatusBadge";
import RiskGauge from "./components/RiskGauge";
import DimensionPanels from "./components/DimensionPanels";
import Timeline from "./components/Timeline";
import EvidencePanels from "./components/EvidencePanels";
import EvidenceToolbar from "./components/EvidenceToolbar";
import RealtimeShield from "./components/RealtimeShield";
import UploadZone from "./components/UploadZone";

type WorkMode = "A" | "B";

function fmt(t: number) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function guessKind(file: File): MediaKind {
  if (file.type.startsWith("video")) return "video";
  if (file.type.startsWith("audio")) return "audio";
  return /\.(mp4|mov|webm|mkv|avi)$/i.test(file.name) ? "video" : "audio";
}

export default function App() {
  const [mode, setMode] = useState<WorkMode>("A");
  const [loaded, setLoaded] = useState<LoadedCase | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingKind, setLoadingKind] = useState<"file" | "url" | null>(null);
  const [loadingStep, setLoadingStep] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [urlInput, setUrlInput] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<number | null>(null);

  function clearUrlTimer() {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }

  /** 使用者主動取消 / 超時自動取消後恢復可操作狀態 */
  function cancelAnalyze() {
    abortRef.current?.abort();
    // 實際狀態復原由 catch/finally 處理，這裡先給即時回饋
    setLoadingStep("正在取消…");
  }

  // 後端健康檢查
  useEffect(() => {
    checkHealth().then((h) => setBackendOk(h !== null));
  }, []);

  // 模式 B 連動 + Demo 快捷: ?demo=celebrity|voice / ?from=extension&session_id=xxx
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const demo = q.get("demo");
    if (demo === "celebrity") {
      setLoaded(demoCelebrity);
      setNotice("已載入內建示範案例（免上傳）。");
      return;
    }
    if (demo === "voice") {
      setLoaded(demoVoice);
      setNotice("已載入內建示範案例（免上傳）。");
      return;
    }
    if (q.get("from") === "extension") {
      const sid = q.get("session_id") ?? "";
      // A. 同源殘留 (外掛 bridge 腳本預填) → B. 後端 session 暫存 (跨網域正解)
      void (async () => {
        try {
          const raw = localStorage.getItem(`deepshield:session:${sid}`);
          if (raw) {
            const data = JSON.parse(raw) as { report: LoadedCase["report"]; mediaKind: MediaKind; label?: string };
            setLoaded({
              report: data.report,
              mediaUrl: null,
              mediaKind: data.mediaKind ?? "video",
              source: "extension",
              label: data.label ?? `外掛送檢（session ${sid || "unknown"}）`,
            });
            setNotice("已接收來自「即時防護盾」外掛的送檢結果（原始影音未隨附，時間軸仍可瀏覽）。");
            return;
          }
        } catch {
          /* localStorage 讀不到就往下走後端 */
        }
        if (sid) {
          try {
            const r = await fetch(`${API_BASE}/api/v1/session/${encodeURIComponent(sid)}`);
            if (r.ok) {
              const data = (await r.json()) as { report: LoadedCase["report"]; mediaKind: MediaKind; label?: string };
              setLoaded({
                report: data.report,
                mediaUrl: null,
                mediaKind: data.mediaKind ?? "video",
                source: "extension",
                label: data.label ?? `外掛送檢（session ${sid}）`,
              });
              setNotice("已從後端暫存載入「即時防護盾」外掛的送檢結果（原始影音未隨附，時間軸仍可瀏覽）。");
              return;
            }
          } catch {
            /* 後端未啟動 → 顯示下方指引 */
          }
        }
        setNotice(
          "收到外掛送檢請求，但找不到該 session 的結果（session_id=" +
            (sid || "空") +
            "）。請確認後端黑窗有開，再回到外掛重新點「送交深度鑑識」。"
        );
      })();
    }
  }, []);

  async function handleFile(file: File) {
    // 若有進行中的網址任務，先中斷再開始新任務
    abortRef.current?.abort();
    clearUrlTimer();
    setError(null);
    setNotice(null);
    setLoading(true);
    setLoadingKind("file");
    setLoadingStep(`上傳 ${file.name}（${(file.size / 1024 / 1024).toFixed(1)} MB）…`);
    const kind = guessKind(file);
    const url = URL.createObjectURL(file);
    try {
      setLoadingStep("後端深度鑑識中（語音／視覺／唇同步／語意四維分析，約 10–60 秒）…");
      const report = await analyzeFile(file);
      setLoaded({ report, mediaUrl: url, mediaKind: kind, source: "upload", label: `上傳鑑定：${file.name}` });
      setCurrentTime(0);
      try {
        localStorage.setItem(
          "deepshield:lastReport",
          JSON.stringify({ report, mediaKind: kind, savedAt: Date.now() })
        );
      } catch {
        /* 配額不足時略過，不影響主流程 */
      }
    } catch (e) {
      URL.revokeObjectURL(url);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setLoadingKind(null);
      setLoadingStep("");
    }
  }

  async function handleUrl() {
    const url = urlInput.trim();
    if (!url) {
      setError("請先貼上影音網址（直連 mp4/mp3 或 YouTube 連結）。");
      return;
    }
    // 中斷上一個未完成的任務
    abortRef.current?.abort();
    clearUrlTimer();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setError(null);
    setNotice(null);
    setLoading(true);
    setLoadingKind("url");
    setLoadingStep(`下載並鑑定網址中（視檔案大小約 30 秒–數分鐘，超過 3 分鐘會自動逾時）…`);
    // 逾時保護：3 分鐘自動中斷，避免 yt-dlp 卡死
    timeoutRef.current = window.setTimeout(() => {
      ctrl.abort();
      setNotice("網址鑑定超過 3 分鐘已自動逾時停止，請改用較短影片或直接下載後上傳檔案。");
    }, 180_000);
    try {
      const report = await analyzeUrl(url, ctrl.signal);
      const playable = /\.(mp4|mov|webm|mp3|wav|m4a|ogg)(\?|#|$)/i.test(url);
      const kind: MediaKind =
        report.skipped_dimensions.includes("visual") && report.skipped_dimensions.includes("avsync")
          ? "audio"
          : guessKind({ name: url, type: "" } as File);
      setLoaded({
        report,
        mediaUrl: playable ? url : null,
        mediaKind: kind,
        source: "url",
        label: `網址鑑定：${url.length > 60 ? url.slice(0, 60) + "…" : url}`,
      });
      setCurrentTime(0);
      setUrlInput("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  }

  function loadDemo(which: "celebrity" | "voice") {    setError(null);
    setLoaded(which === "celebrity" ? demoCelebrity : demoVoice);
    setCurrentTime(0);
    setNotice("已載入內建示範案例：圖表、熱力圖與時間軸皆可互動，點色塊可跳轉播放。");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function goHome() {
    if (loaded?.source === "upload" && loaded.mediaUrl) URL.revokeObjectURL(loaded.mediaUrl);
    setLoaded(null);
    setCurrentTime(0);
    setNotice(null);
    setError(null);
  }

  function onSeek(t: number) {
    setCurrentTime(t);
    const el = videoRef.current ?? audioRef.current;
    if (el) {
      try {
        el.currentTime = Math.min(t, el.duration || t);
        void el.play().catch(() => undefined);
      } catch {
        /* 尚未載入 metadata 時僅移動播放頭 */
      }
    }
  }

  const report = loaded?.report ?? null;
  const duration = report?.duration ?? 0;

  return (
    <div className="min-h-screen">
      {/* 頂欄 */}
      <header className="no-print sticky top-0 z-10 border-b border-line bg-ink/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-rose-500 to-amber-500 text-white">
            <Shield size={22} />
          </div>
          <div>
            <h1 className="text-lg font-extrabold tracking-wide">DeepShield 深度鑑識中心</h1>
            <p className="text-xs text-slate-500">模式 A · 事後鑑定所 — AI 語音與深偽影片雙層防禦</p>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${
                backendOk === null
                  ? "border-line text-slate-400"
                  : backendOk
                    ? "border-emerald-500/40 text-emerald-300"
                    : "border-red-500/40 text-red-300"
              }`}
            >
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  backendOk === null ? "bg-slate-500" : backendOk ? "bg-emerald-400" : "bg-red-400"
                }`}
              />
              {backendOk === null ? "檢測後端中…" : backendOk ? `後端連線正常` : "後端未連線"}
            </span>
            <span className="hidden font-mono text-slate-500 md:inline">{API_BASE}</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        {notice && (
          <div className="flex items-start gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-200">
            <Radio size={16} className="mt-0.5 shrink-0" />
            <span>{notice}</span>
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}

        {!loaded || !report ? (
          <>
            {/* 首頁：上傳 + Demo */}
            <div className="rounded-2xl border border-line bg-panel p-6 text-center md:p-10">
              <h2 className="text-2xl font-extrabold md:text-3xl">
                上傳可疑影音，<span className="text-rose-400">法醫級鑑識</span>一次看穿
              </h2>
              <p className="mx-auto mt-2 max-w-2xl text-sm text-slate-400">
                四維分析：語音物理特徵 · 視覺換臉破綻 · 唇音同步 · 詐騙話術語意，
                輸出可解釋性鐵證（頻譜圖 / 熱力圖 / 異常時間軸 / 螢光筆逐字稿）。
              </p>
              <div className="mx-auto mt-6 max-w-3xl">
                <UploadZone onFile={handleFile} loading={loading} />
              </div>
              {loading && (
                <p className="mt-3 flex items-center justify-center gap-2 text-sm text-sky-300">
                  <Loader2 className="animate-spin" size={16} />
                  {loadingStep}
                </p>
              )}
              <div className="mx-auto mt-4 flex max-w-3xl gap-2">
                <div className="flex flex-1 items-center gap-2 rounded-xl border border-line bg-ink px-3 py-2.5">
                  <Link2 size={16} className="shrink-0 text-slate-500" />
                  <input
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !loading) void handleUrl();
                    }}
                    placeholder="或貼上網址鑑定：直連 mp4/mp3，或 YouTube 連結…"
                    disabled={loading}
                    className="w-full bg-transparent text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none"
                  />
                </div>
                <button
                  onClick={() => void handleUrl()}
                  disabled={loading || !urlInput.trim()}
                  className="shrink-0 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 px-5 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-40"
                >
                  鑑定網址
                </button>
              </div>
              <div className="mx-auto mt-6 grid max-w-3xl gap-3 text-left md:grid-cols-2">
                <button
                  onClick={() => loadDemo("celebrity")}
                  disabled={loading}
                  className="group rounded-xl border border-orange-500/30 bg-gradient-to-br from-orange-500/15 to-rose-500/10 p-4 transition hover:border-orange-400 disabled:opacity-50"
                >
                  <span className="flex items-center gap-2 font-bold text-orange-200">
                    <Film size={18} />
                    載入範例：名人投資詐騙 Deepfake
                    <Sparkles size={14} className="text-orange-300" />
                  </span>
                  <span className="mt-1 block text-xs text-slate-400">
                    8 秒展示影片 · 換臉閃爍＋嘴型不同步＋保證獲利話術，一鍵呈現完整鐵證
                  </span>
                </button>
                <button
                  onClick={() => loadDemo("voice")}
                  disabled={loading}
                  className="group rounded-xl border border-amber-500/30 bg-gradient-to-br from-amber-500/15 to-yellow-500/10 p-4 transition hover:border-amber-400 disabled:opacity-50"
                >
                  <span className="flex items-center gap-2 font-bold text-amber-200">
                    <Mic size={18} />
                    載入範例：AI 語音親友借錢詐騙
                    <Sparkles size={14} className="text-amber-300" />
                  </span>
                  <span className="mt-1 block text-xs text-slate-400">
                    8 秒展示音檔 · 高頻截斷＋無換氣＋急用錢話術，不用上傳即看全圖表
                  </span>
                </button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              {[
                { t: "1 · 上傳或一鍵載入範例", d: "拖曳檔案直連後端 /api/v1/analyze/deep，或用範例秒看效果。" },
                { t: "2 · 四維鑑識", d: "語音、視覺、唇同步、語意並行分析，加權輸出偽造機率。" },
                { t: "3 · 鐵證互動", d: "點時間軸色塊跳轉播放，對照頻譜圖、熱力圖與逐字稿。" },
              ].map((s) => (
                <div key={s.t} className="rounded-xl border border-line bg-panel p-4">
                  <p className="font-bold text-slate-200">{s.t}</p>
                  <p className="mt-1 text-sm text-slate-400">{s.d}</p>
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            {/* 報告頁 */}
            <div className="no-print flex flex-wrap items-center gap-2">
              <button
                onClick={goHome}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500"
              >
                <RotateCcw size={14} />
                重新鑑定
              </button>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                {loaded.label}
              </span>
              {duration > 0 && (
                <span className="font-mono text-xs text-slate-500">片長 {duration.toFixed(1)}s</span>
              )}
              <div className="ml-1">
                <StatusBadge status={report.status} />
              </div>
            </div>

            {/* 證據輸出與防詐分享工具列 */}
            <EvidenceToolbar report={report} sourceLabel={loaded.label} />

            {/* 頂部總覽 */}
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="flex flex-col items-center justify-center rounded-xl border border-line bg-panel p-4">
                <RiskGauge value={report.fake_probability} />
                <div className="mt-1">
                  <StatusBadge status={report.status} big />
                </div>
                <p className="mt-2 text-sm text-slate-400">
                  信任分數 <span className="font-mono font-bold text-slate-200">{report.trust_score.toFixed(1)}</span>
                  <span className="text-slate-600"> / 100</span>
                </p>
              </div>
              <div className="lg:col-span-2">
                <DimensionPanels report={report} />
              </div>
            </div>

            {/* 播放器 */}
            <div className="rounded-xl border border-line bg-panel p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-300">送檢影音</h3>
              {loaded.mediaUrl ? (
                loaded.mediaKind === "video" ? (
                  <video
                    ref={videoRef}
                    src={loaded.mediaUrl}
                    controls
                    className="max-h-[420px] w-full rounded-lg bg-black"
                    onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                  />
                ) : (
                  <audio
                    ref={audioRef}
                    src={loaded.mediaUrl}
                    controls
                    className="w-full"
                    onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                  />
                )
              ) : (
                <p className="text-sm text-slate-500">
                  {loaded.source === "extension"
                    ? "此結果來自外掛送檢，原始影音未隨附 — 下方時間軸仍可瀏覽各異常段落。"
                    : "此網址來源無法直接在頁面播放 — 下方時間軸仍可瀏覽各異常段落。"}
                </p>
              )}
              <p className="mt-1 font-mono text-xs text-slate-500">
                {fmt(currentTime)} / {fmt(duration)}
              </p>
            </div>

            {/* 時間軸 */}
            <Timeline
              events={report.timeline}
              duration={duration}
              currentTime={currentTime}
              onSeek={onSeek}
            />

            {/* 鐵證區 */}
            <EvidencePanels report={report} />

            {/* 原始 JSON（除錯用） */}
            <details className="rounded-xl border border-line bg-panel p-4 text-xs">
              <summary className="cursor-pointer text-slate-400">原始報告 JSON（除錯用，點擊展開）</summary>
              <pre className="mt-2 max-h-72 overflow-auto rounded bg-black/40 p-3 font-mono text-[11px] text-slate-400">
                {JSON.stringify(
                  { ...report, dimensions: { ...report.dimensions, audio: { ...report.dimensions.audio, spectrogram_b64: `[${(report.dimensions.audio.spectrogram_b64 ?? "").length} chars]` }, visual: { ...report.dimensions.visual, heatmap_b64: `[${(report.dimensions.visual.heatmap_b64 ?? "").length} chars]` } } },
                  null,
                  2
                )}
              </pre>
            </details>
          </>
        )}
      </main>

      <footer className="border-t border-line py-4 text-center text-xs text-slate-600">
        DeepShield 模式 A · 鑑識結果僅供風險參考，不構成法律證據
      </footer>
    </div>
  );
}
