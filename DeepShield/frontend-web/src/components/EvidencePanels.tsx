import React from "react";
import { ImageOff } from "lucide-react";
import { imgSrc } from "../api";
import type { DeepReport, ScamSpan, TranscriptSegment } from "../types";

function Empty({ text }: { text: string }) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg bg-slate-900/60 text-sm text-slate-500">
      <ImageOff size={20} />
      {text}
    </div>
  );
}

/** 逐字稿螢光筆：把命中 spans 的關鍵詞標成 <mark>. */
function HighlightedLine({ text, spans }: { text: string; spans: ScamSpan[] }) {
  interface M { i: number; len: number; kw: string }
  const matches: M[] = [];
  for (const s of spans) {
    const needle = s.text || s.keyword;
    if (!needle) continue;
    let idx = text.indexOf(needle);
    while (idx !== -1) {
      matches.push({ i: idx, len: needle.length, kw: s.keyword });
      idx = text.indexOf(needle, idx + 1);
    }
  }
  if (matches.length === 0) return <>{text}</>;
  matches.sort((a, b) => a.i - b.i);
  const merged: M[] = [];
  for (const m of matches) {
    const last = merged[merged.length - 1];
    if (last && m.i <= last.i + last.len) {
      last.len = Math.max(last.len, m.i + m.len - last.i);
    } else {
      merged.push({ ...m });
    }
  }
  const out: React.ReactNode[] = [];
  let cur = 0;
  merged.forEach((m, k) => {
    if (m.i > cur) out.push(<span key={`t${k}`}>{text.slice(cur, m.i)}</span>);
    out.push(
      <mark key={`m${k}`} className="scam" title={`詐騙關鍵詞: ${m.kw}`}>
        {text.slice(m.i, m.i + m.len)}
      </mark>
    );
    cur = m.i + m.len;
  });
  if (cur < text.length) out.push(<span key="tail">{text.slice(cur)}</span>);
  return <>{out}</>;
}

export function TranscriptView({ report }: { report: DeepReport }) {
  const sem = report.dimensions.semantic;
  const segs: TranscriptSegment[] = sem.transcript ?? [];
  const spans: ScamSpan[] = sem.spans ?? [];
  if (!sem.stt_available) {
    return (
      <div className="rounded-xl border border-line bg-panel p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-300">防詐語意逐字稿</h3>
        <p className="text-sm text-slate-500">
          後端未安裝 faster-whisper，本次未產生逐字稿（語意維度以 0 計，不影響其他維度）。
          {sem.note ? ` — ${sem.note}` : ""}
        </p>
      </div>
    );
  }
  if (segs.length === 0) {
    return (
      <div className="rounded-xl border border-line bg-panel p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-300">防詐語意逐字稿</h3>
        <p className="text-sm text-slate-500">無逐字稿內容。</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-300">
        防詐語意逐字稿
        <span className="ml-2 text-xs font-normal text-slate-500">
          黃色螢光筆＝觸發詞彙（共 {spans.length} 處）
        </span>
      </h3>
      <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
        {segs.map((s, i) => {
          const rel = spans.filter((p) => p.start < s.end && p.end > s.start);
          return (
            <div key={i} className="flex gap-3 rounded-lg bg-slate-900/60 px-3 py-2 text-sm leading-relaxed">
              <span className="shrink-0 font-mono text-xs text-sky-400/90">
                [{s.start.toFixed(1)}s]
              </span>
              <p className="text-slate-200">
                <HighlightedLine text={s.text} spans={rel} />
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function EvidencePanels({ report }: { report: DeepReport }) {
  const audio = report.dimensions.audio;
  const visual = report.dimensions.visual;
  const spec = imgSrc(audio.spectrogram_b64, "png");
  const heat = imgSrc(visual.heatmap_b64, "jpg");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-line bg-panel p-4">
        <h3 className="mb-1 text-sm font-semibold text-slate-300">
          音訊梅爾頻譜斷層標示圖
        </h3>
        <p className="mb-2 text-xs text-slate-500">
          紅框＝疑似異常窗（高頻能量斷層 / 數位靜音剪接點）。AI 合成音常在高頻出現不自然斷層。
        </p>
        {spec ? (
          <img src={spec} alt="mel spectrogram" className="w-full rounded-lg border border-line" />
        ) : (
          <Empty text="無頻譜圖（音軌缺失或分析失敗）" />
        )}
      </div>
      <div className="rounded-xl border border-line bg-panel p-4">
        <h3 className="mb-1 text-sm font-semibold text-slate-300">
          原始畫面 vs. 換臉邊界熱力圖
        </h3>
        <p className="mb-2 text-xs text-slate-500">
          熱區＝臉緣梯度異常（過度平滑的融合邊界）與幀間閃爍位置。
        </p>
        {heat ? (
          <img src={heat} alt="face heatmap" className="w-full rounded-lg border border-line" />
        ) : (
          <Empty text={visual.note ?? "無熱力圖（未偵測到人臉或為純音檔）"} />
        )}
      </div>
      <div className="lg:col-span-2">
        <TranscriptView report={report} />
      </div>
    </div>
  );
}
