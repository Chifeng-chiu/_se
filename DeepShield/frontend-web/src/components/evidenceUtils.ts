import { imgSrc } from "../api";
import type { DeepReport, Verdict } from "../types";

/** 狀態配色 (圖卡 + 列印報表共用) */
export const STATUS_THEME: Record<Verdict, { bg: string; fg: string; label: string; bar: string }> = {
  DANGER: { bg: "#DC2626", fg: "#FFFFFF", label: "DANGER 高度疑似偽造", bar: "#EF4444" },
  WARNING: { bg: "#D97706", fg: "#FFFFFF", label: "WARNING 可疑", bar: "#F59E0B" },
  SAFE: { bg: "#059669", fg: "#FFFFFF", label: "SAFE 暫無明顯偽造", bar: "#10B981" },
};

export function shortHash(hash: string | undefined): string {
  if (!hash) return "未提供 (示範案例)";
  return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
}

export function analyzedAtText(report: DeepReport): string {
  if (report.analyzed_at) {
    try {
      return new Date(report.analyzed_at).toLocaleString("zh-TW", { hour12: false });
    } catch {
      return report.analyzed_at;
    }
  }
  return new Date().toLocaleString("zh-TW", { hour12: false });
}

/** 取前 N 條最嚴重鐵證: 詐騙關鍵詞優先, 其次時間軸前段 */
export function topEvidence(report: DeepReport, n = 3): string[] {
  const out: string[] = [];
  const semHits = report.dimensions.semantic.hits ?? [];
  for (const h of semHits.slice(0, n)) {
    out.push(`觸發詐騙關鍵字:${h.keyword}`);
    if (out.length >= n) return out;
  }
  const prio: Record<string, number> = {
    SCAM_KEYWORD: 0,
    LIP_SYNC_MISMATCH: 1,
    FACE_FLICKER: 2,
    AUDIO_ANOMALY: 3,
  };
  const sorted = [...(report.timeline ?? [])].sort(
    (a, b) => (prio[a.type] ?? 9) - (prio[b.type] ?? 9) || a.start - b.start
  );
  for (const ev of sorted) {
    const label =
      ev.type === "SCAM_KEYWORD"
        ? ev.description
        : ev.type === "LIP_SYNC_MISMATCH"
          ? `嘴型與聲音嚴重不同步 (${ev.start.toFixed(1)}s)`
          : ev.type === "FACE_FLICKER"
            ? `臉部閃爍疑似換臉 (${ev.start.toFixed(1)}s)`
            : ev.type === "AUDIO_ANOMALY"
              ? `偵測到 AI 語音合成特徵 (${ev.start.toFixed(1)}s)`
              : ev.description;
    if (!out.includes(label)) out.push(label);
    if (out.length >= n) break;
  }
  while (out.length < n) out.push("無更多異常事件");
  return out.slice(0, n);
}

export function loadImage(src: string): Promise<HTMLImageElement | null> {
  if (!src) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** 報告中的視覺鐵證圖 (熱力圖優先, 其次頻譜圖) */
export async function loadEvidenceThumbs(report: DeepReport) {
  const heatSrc = imgSrc(report.dimensions.visual.heatmap_b64, "jpg");
  const specSrc = imgSrc(report.dimensions.audio.spectrogram_b64, "png");
  const [heat, spec] = await Promise.all([loadImage(heatSrc), loadImage(specSrc)]);
  return { heat, spec, heatSrc, specSrc };
}
