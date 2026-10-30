import type { TimelineEvent } from "../types";

export const EVENT_STYLE: Record<string, { color: string; label: string }> = {
  AUDIO_ANOMALY: { color: "#ef4444", label: "語音異常" },
  FACE_FLICKER: { color: "#f97316", label: "換臉破綻" },
  LIP_SYNC_MISMATCH: { color: "#a855f7", label: "嘴型不同步" },
  SCAM_KEYWORD: { color: "#eab308", label: "詐騙關鍵詞" },
  SCENE_FLICKER: { color: "#fb7185", label: "場景閃爍 (AI 生成疑慮)" },
};

function styleOf(type: string) {
  return EVENT_STYLE[type] ?? { color: "#38bdf8", label: type };
}

interface Props {
  events: TimelineEvent[];
  duration: number;
  currentTime: number;
  onSeek: (t: number) => void;
}

export default function Timeline({ events, duration, currentTime, onSeek }: Props) {
  const dur = Math.max(duration, 0.01);
  const sorted = [...events].sort((a, b) => a.start - b.start);
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-slate-300">互動式異常時間軸（點擊色塊跳轉播放）</h3>
        <div className="ml-auto flex flex-wrap gap-2 text-[11px] text-slate-400">
          {Object.entries(EVENT_STYLE).map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: v.color }} />
              {v.label}
            </span>
          ))}
        </div>
      </div>

      {/* 軌道 */}
      <div className="relative h-12 overflow-hidden rounded-md bg-slate-900/80">
        {/* 秒刻度 */}
        {Array.from({ length: Math.min(17, Math.floor(dur) + 1) }, (_, i) => {
          const sec = Math.round((dur / Math.min(16, Math.max(1, Math.floor(dur)))) * i * 10) / 10;
          if (sec > dur) return null;
          return (
            <span
              key={i}
              className="absolute top-0 text-[10px] text-slate-500"
              style={{ left: `${(sec / dur) * 100}%` }}
            >
              {sec}s
            </span>
          );
        })}
        {sorted.map((e, i) => {
          const s = styleOf(e.type);
          const left = Math.max(0, (e.start / dur) * 100);
          const width = Math.max(1.2, ((e.end - e.start) / dur) * 100);
          return (
            <button
              key={i}
              title={`${s.label} ${e.start.toFixed(1)}s–${e.end.toFixed(1)}s：${e.description}（點擊跳轉）`}
              onClick={() => onSeek(e.start + 0.01)}
              className="absolute top-5 h-5 rounded-sm opacity-80 transition hover:opacity-100 hover:brightness-125"
              style={{ left: `${left}%`, width: `${width}%`, background: s.color }}
            />
          );
        })}
        {/* 播放頭 */}
        <div
          className="pointer-events-none absolute top-0 h-full w-0.5 bg-white/90"
          style={{ left: `${Math.min(100, (currentTime / dur) * 100)}%` }}
        />
      </div>

      {/* 事件清單 */}
      <div className="mt-3 max-h-44 space-y-1 overflow-y-auto pr-1">
        {sorted.length === 0 && <p className="text-sm text-slate-500">無異常事件 — 時間軸乾淨。</p>}
        {sorted.map((e, i) => {
          const s = styleOf(e.type);
          return (
            <button
              key={i}
              onClick={() => onSeek(e.start + 0.01)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs hover:bg-slate-800/70"
            >
              <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: s.color }} />
              <span className="shrink-0 font-mono text-slate-400">
                {e.start.toFixed(1)}s–{e.end.toFixed(1)}s
              </span>
              <span className="shrink-0 font-semibold" style={{ color: s.color }}>
                {s.label}
              </span>
              <span className="truncate text-slate-300">{e.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
