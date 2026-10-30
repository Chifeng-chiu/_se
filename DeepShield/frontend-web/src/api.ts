import type { DeepReport } from "./types";

/** 後端位址: 優先吃 .env 的 VITE_API_BASE, 否則直連本機 8000. */
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export async function analyzeFile(file: File, signal?: AbortSignal): Promise<DeepReport> {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1/analyze/deep`, {
      method: "POST",
      body: form,
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new Error(
      `連不上後端 ${API_BASE}：請確認已雙擊桌面「DeepShield 啟動」且黑窗沒有關閉。`
    );
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`後端回應 ${res.status}：${text.slice(0, 200)}`);
  }
  return (await res.json()) as DeepReport;
}

/** 用網址鑑定：直連影音檔或 YouTube 連結（後端下載後走同一套深度鑑識）。支援 AbortSignal 取消。 */
export async function analyzeUrl(url: string, signal?: AbortSignal): Promise<DeepReport> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1/analyze/url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new Error(
      `連不上後端 ${API_BASE}：請確認已雙擊桌面「DeepShield 啟動」且黑窗沒有關閉。`
    );
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    // 後端錯誤多半包在 {"detail": "..."}，盡量取出可讀訊息
    try {
      const j = JSON.parse(text) as { detail?: string };
      if (j.detail) throw new Error(j.detail.slice(0, 200));
    } catch (e) {
      if (e instanceof Error && !e.message.startsWith("後端回應")) throw e;
    }
    throw new Error(`後端回應 ${res.status}：${text.slice(0, 200)}`);
  }
  return (await res.json()) as DeepReport;
}

export async function checkHealth(): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`);
    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** 後端圖欄位可能是裸 base64、data URL、或 /demo/… 路徑, 統一轉成 <img> 可用的 src. */
export function imgSrc(raw: string | undefined, kind: "png" | "jpg"): string {
  if (!raw) return "";
  if (raw.startsWith("data:") || raw.startsWith("http") || raw.startsWith("/")) {
    return raw;
  }
  const mime = kind === "png" ? "image/png" : "image/jpeg";
  return `data:${mime};base64,${raw}`;
}

/** WS 位址: http(s) → ws(s), 供模式 B 即時監控使用 */
export const WS_URL = `${API_BASE.replace(/^http/, "ws")}/api/v1/ws/realtime-scan`;

export interface RealtimeResult {
  timestamp: number;
  trust_score: number;
  status: "SAFE" | "WARNING" | "DANGER";
  alerts: string[];
  transcript_snippet: string;
}
